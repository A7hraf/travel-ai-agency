"""Business insights: figures of one travel company, figures of the whole platform, and written analyses by the AI.

The owner's view of the platform is built from totals per company only: never chat texts, names or comments.
A company's view of itself also shows what its customers search for and its low ratings, which are its own data.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from datetime import timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..addons import enabled_addons
from ..ai.llm import LLMError, MockTravelLLM, clean_content, get_llm_client
from ..ai.planner import learned_stats
from ..b2b import b2b_settings
from .requests import WAITING_FOR_STAFF
from ..models import (
    Company,
    CompanyStatus,
    Conversation,
    ConversationStatus,
    Customer,
    InsightReport,
    Message,
    MessageKind,
    Subscription,
    Ticket,
    TicketStatus,
    TravelPackage,
    TripFeedback,
    TripRequest,
    TripRequestStatus,
    User,
    utcnow,
)

log = logging.getLogger(__name__)
PAID = (TicketStatus.PAID, TicketStatus.CONFIRMED)
STOP = set("the a an to in for and or of with from me my i we our trip trips package packages travel please want "
           "need looking show any some best cheap price prices days day night nights omr".split())


def _money(v) -> float:
    return round(float(v or 0), 3)


def _searches(db: Session, company_id: int, since) -> list[tuple[str, int]]:
    """What customers asked the AI to find (the words of its package searches)."""
    metas = db.scalars(select(Message.meta).join(Conversation, Conversation.id == Message.conversation_id).where(
        Conversation.company_id == company_id, Message.kind == MessageKind.TOOL_CALL, Message.created_at >= since)
        .limit(3000)).all()
    words: Counter[str] = Counter()
    for meta in metas:
        for call in (meta or {}).get("tool_calls", []) if isinstance(meta, dict) else []:
            fn = call.get("function", {}) if isinstance(call, dict) else {}
            if fn.get("name") != "search_packages":
                continue
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except (TypeError, json.JSONDecodeError):
                continue
            text = " ".join(str(args.get(k) or "") for k in ("query", "destination", "category"))
            for w in re.findall(r"[^\W\d_]{3,}", text.lower()):
                if w not in STOP:
                    words[w] += 1
    return words.most_common(12)


def _quotation_stats(tickets: list[Ticket]) -> dict:
    """How clients answer quotations: sent, approved, rejected, and how many rounds it takes."""
    quoted = [t for t in tickets if t.quote_round]
    approved = [t for t in quoted if t.status in (TicketStatus.PENDING_PAYMENT, TicketStatus.IN_PROGRESS,
                                                  TicketStatus.PAID, TicketStatus.CONFIRMED)]
    return {"requests_quoted": len(quoted), "approved": len(approved),
            "rejected": sum(1 for t in quoted if t.status == TicketStatus.REJECTED),
            "approval_rate": round(len(approved) / len(quoted), 3) if quoted else None,
            "average_rounds": round(sum(t.quote_round for t in quoted) / len(quoted), 2) if quoted else None}


def company_metrics(db: Session, company: Company, days: int = 90, private: bool = True) -> dict:
    """The figures of one company over the last `days`. `private=False` leaves out its customers' words."""
    since = utcnow() - timedelta(days=days)
    cid = company.id
    convs = dict(db.execute(select(Conversation.channel, func.count(Conversation.id)).where(
        Conversation.company_id == cid, Conversation.created_at >= since).group_by(Conversation.channel)).all())
    total_convs = sum(convs.values())
    handed = db.scalar(select(func.count(Conversation.id)).where(
        Conversation.company_id == cid, Conversation.created_at >= since,
        Conversation.status == ConversationStatus.HUMAN)) or 0
    new_customers = db.scalar(select(func.count(Customer.id)).where(Customer.company_id == cid,
                                                                    Customer.created_at >= since)) or 0
    tickets = db.scalars(select(Ticket).where(Ticket.company_id == cid, Ticket.created_at >= since)).all()
    by_status = Counter(t.status for t in tickets)
    paid = [t for t in tickets if t.status in PAID]
    revenue = sum((t.total_price for t in paid), Decimal(0))
    buyers = len({t.customer_id for t in tickets})
    customers_who_chatted = db.scalar(select(func.count(func.distinct(Conversation.customer_id))).where(
        Conversation.company_id == cid, Conversation.created_at >= since)) or 0
    top_packages = Counter(t.package_title for t in paid).most_common(5)
    active_packages = db.scalars(select(TravelPackage.title).where(TravelPackage.company_id == cid,
                                                                   TravelPackage.is_active.is_(True))).all()
    booked_titles = {t.package_title for t in tickets}
    fb = db.execute(select(func.avg(TripFeedback.rating), func.count(TripFeedback.id)).where(
        TripFeedback.company_id == cid, TripFeedback.created_at >= since)).one()
    members = dict(db.execute(select(Customer.member_level, func.count(Customer.id)).where(
        Customer.company_id == cid, Customer.member_level.is_not(None)).group_by(Customer.member_level)).all())
    requests = db.scalars(select(TripRequest).where(TripRequest.company_id == cid, TripRequest.created_at >= since)).all()
    req_status = Counter(r.status for r in requests)
    margin = Decimal(0)
    for r in requests:
        if r.status in (TripRequestStatus.APPROVED, TripRequestStatus.BOOKED, TripRequestStatus.COMPLETED):
            chosen = [o for o in r.options if o.chosen]
            if chosen and all(o.price is not None and o.cost_price is not None for o in chosen):
                margin += sum((o.price - o.cost_price for o in chosen), Decimal(0))
    m = {
        "company": company.name, "days": days, "currency": company.currency or "OMR",
        "chats": {"total": total_convs, "by_channel": convs, "handed_to_staff": handed,
                  "handover_rate": round(handed / total_convs, 3) if total_convs else None},
        "customers": {"new": new_customers, "chatted": customers_who_chatted, "booked": buyers,
                      "conversion_rate": round(buyers / customers_who_chatted, 3) if customers_who_chatted else None},
        "bookings": {"total": len(tickets), "by_status": dict(by_status), "paid_or_confirmed": len(paid),
                     "revenue": _money(revenue), "average_value": _money(revenue / len(paid)) if paid else None,
                     "cancelled": by_status.get(TicketStatus.CANCELLED, 0)},
        "packages": {"active": len(active_packages), "top_booked": top_packages,
                     "never_booked": [t for t in active_packages if t not in booked_titles][:10]},
        "feedback": {"average": round(float(fb[0]), 2) if fb[0] is not None else None, "count": fb[1]},
        "members": members,
        "business_requests": {"total": len(requests), "by_status": dict(req_status), "margin": _money(margin)},
        "quotations": _quotation_stats(tickets),
        "ai_learned": {k: v[:3] for k, v in learned_stats(db, cid).items()},
    }
    if private:
        m["customers_searched_for"] = _searches(db, cid, since)
        m["low_ratings"] = [{"rating": f.rating, "comment": f.comment} for f in db.scalars(
            select(TripFeedback).where(TripFeedback.company_id == cid, TripFeedback.created_at >= since,
                                       TripFeedback.rating <= 3).order_by(TripFeedback.created_at.desc()).limit(5)).all()]
        m["requests_waiting_for_staff"] = db.scalar(select(func.count(Ticket.id)).where(
            Ticket.company_id == cid, Ticket.status.in_(WAITING_FOR_STAFF))) or 0
    return m


# --- Platform owner -----------------------------------------------------------------------------------

def _opportunities(row: dict) -> list[str]:
    """Simple rules that point the owner to companies to help, upsell or save."""
    tips = []
    if row["status"] != CompanyStatus.ACTIVE:
        return tips
    if row["chats_30d"] == 0:
        tips.append("No chats in 30 days: at risk; call them and help them share their page and WhatsApp.")
    elif row["bookings_30d"] == 0:
        tips.append("Chats but no bookings: offer AI training help and better packages (conversion coaching).")
    if row["conversion"] is not None and row["conversion"] < 0.05 and row["chats_30d"] >= 20:
        tips.append("Many chats, few bookings: review their packages and prices with them.")
    if row["handover_rate"] is not None and row["handover_rate"] > 0.35:
        tips.append("The AI hands over a lot: add trained answers and company knowledge for them.")
    if row["rating"] is not None and row["rating"] < 4:
        tips.append("Ratings below 4: service quality follow-up.")
    if row["chats_30d"] >= 100 and row["plan"] and "starter" in row["plan"].lower():
        tips.append("High use on Starter: propose the Business plan.")
    if row["repeat_customers"] >= 5 and "members" not in row["addons"]:
        tips.append("Has repeat customers: offer the Members community.")
    if row["bookings_30d"] >= 10 and "insights" not in row["addons"]:
        tips.append("Growing: offer AI insights.")
    return tips


def platform_overview(db: Session) -> dict:
    since30 = utcnow() - timedelta(days=30)
    rows = []
    for company in db.scalars(select(Company).order_by(Company.name)).all():
        cid = company.id
        chats = db.scalar(select(func.count(Conversation.id)).where(Conversation.company_id == cid,
                                                                    Conversation.created_at >= since30)) or 0
        handed = db.scalar(select(func.count(Conversation.id)).where(Conversation.company_id == cid,
                                                                     Conversation.created_at >= since30,
                                                                     Conversation.status == ConversationStatus.HUMAN)) or 0
        tickets = db.scalars(select(Ticket).where(Ticket.company_id == cid, Ticket.created_at >= since30)).all()
        paid = [t for t in tickets if t.status in PAID]
        chatted = db.scalar(select(func.count(func.distinct(Conversation.customer_id))).where(
            Conversation.company_id == cid, Conversation.created_at >= since30)) or 0
        repeat = db.scalar(select(func.count()).select_from(
            select(Ticket.customer_id).where(Ticket.company_id == cid, Ticket.status.in_(PAID))
            .group_by(Ticket.customer_id).having(func.count(Ticket.id) >= 2).subquery())) or 0
        rating = db.scalar(select(func.avg(TripFeedback.rating)).where(TripFeedback.company_id == cid))
        last = db.scalar(select(func.max(Conversation.last_message_at)).where(Conversation.company_id == cid))
        sub = db.scalar(select(Subscription).where(Subscription.company_id == cid))
        staff = db.scalar(select(func.count(User.id)).where(User.company_id == cid, User.partner_id.is_(None),
                                                            User.is_active.is_(True))) or 0
        row = {
            "id": cid, "name": company.name, "slug": company.slug, "status": company.status,
            "plan": sub.plan.name if sub else None, "subscription": sub.status if sub else None,
            "staff": staff, "chats_30d": chats, "bookings_30d": len(tickets), "paid_30d": len(paid),
            "revenue_30d": _money(sum((t.total_price for t in paid), Decimal(0))),
            "conversion": round(len({t.customer_id for t in tickets}) / chatted, 3) if chatted else None,
            "handover_rate": round(handed / chats, 3) if chats else None,
            "rating": round(float(rating), 2) if rating is not None else None,
            "repeat_customers": repeat, "last_activity": last.isoformat() if last else None,
            "addons": enabled_addons(company), "b2b": b2b_settings(company).enabled,
        }
        row["opportunities"] = _opportunities(row)
        rows.append(row)
    active = [r for r in rows if r["status"] == CompanyStatus.ACTIVE]
    totals = {
        "companies": len(rows), "active": len(active), "chats_30d": sum(r["chats_30d"] for r in rows),
        "bookings_30d": sum(r["bookings_30d"] for r in rows),
        "revenue_30d_of_agencies": _money(sum(r["revenue_30d"] for r in rows)),
        "at_risk": sum(1 for r in active if r["chats_30d"] == 0),
        "addon_use": dict(Counter(a for r in rows for a in r["addons"])),
    }
    return {"totals": totals, "companies": rows}


# --- Written analyses ---------------------------------------------------------------------------------

COMPANY_PROMPT = """You are a senior business analyst for travel agencies in Oman and the Gulf. Below are the \
figures of the agency "{name}" for the last {days} days (JSON). Write a clear, practical report in {language} \
for the agency's owner, with these sections (Markdown headings):
1. Summary (3 bullet points)
2. What your customers want (needs, destinations, behaviour, culture: use their searches and ratings)
3. What to improve (AI answers, packages, prices, service, response)
4. Growth plan for the next 90 days (concrete steps, numbers where possible)
5. Marketing ideas (channels, seasons in Oman and the Gulf, offers)
Use only these figures; say when there is too little data. Be direct and specific; no generic advice."""

OWNER_PROMPT = """You are the strategy advisor of Ghanjah, a platform that gives travel agencies in Oman and the Gulf \
an AI travel consultant, WhatsApp/Instagram chat, bookings, business accounts, members and insights. Below are \
totals per agency for the last 30 days (JSON, no customer data). Write a report in {language} for the platform \
owner, with these sections (Markdown headings):
1. Platform health (3 bullet points)
2. Agencies to act on now (who, why, what to offer: growth help, plan upgrade, add-on, rescue)
3. What the travel business is telling us (trends across agencies)
4. Features to build or improve next (ranked, with the reason from the data)
5. Marketing and sales plan for the platform (who to target, message, offers)
Use only these figures; be direct and specific."""

LANGS = {"en": "English", "ar": "Arabic (Gulf-friendly Modern Standard Arabic)"}


def _fallback_report(metrics: dict, audience: str, lang: str) -> str:
    """A short rule-based report when no AI server is set up."""
    if audience == "owner":
        t = metrics["totals"]
        lines = [f"## {'صحة المنصة' if lang == 'ar' else 'Platform health'}",
                 f"- {t['active']}/{t['companies']} active · {t['chats_30d']} chats · {t['bookings_30d']} bookings (30 days)",
                 f"- {t['at_risk']} at risk", "", f"## {'وكالات تحتاج متابعة' if lang == 'ar' else 'Agencies to act on'}"]
        for r in metrics["companies"]:
            for tip in r["opportunities"]:
                lines.append(f"- **{r['name']}**: {tip}")
        return "\n".join(lines)
    b, c = metrics["bookings"], metrics["customers"]
    return "\n".join([
        f"## {'الملخص' if lang == 'ar' else 'Summary'}",
        f"- {metrics['chats']['total']} chats · {b['total']} bookings · {b['revenue']} {metrics['currency']}",
        f"- Conversion: {c['conversion_rate']}", f"- Rating: {metrics['feedback']['average']}",
        "", f"## {'ما يبحث عنه العملاء' if lang == 'ar' else 'What customers search for'}",
        *[f"- {w} ({n})" for w, n in metrics.get("customers_searched_for", [])[:8]],
    ])


def write_report(db: Session, metrics: dict, audience: str, lang: str, company: Company | None,
                 created_by: str) -> InsightReport:
    llm = get_llm_client()
    if isinstance(llm, MockTravelLLM):
        content = _fallback_report(metrics, audience, lang)
    else:
        prompt = (OWNER_PROMPT.format(language=LANGS[lang]) if audience == "owner"
                  else COMPANY_PROMPT.format(name=company.name, days=metrics["days"], language=LANGS[lang]))
        try:
            resp = llm.chat([{"role": "system", "content": prompt},
                             {"role": "user", "content": json.dumps(metrics, ensure_ascii=False, default=str)}], [])
        except LLMError as exc:
            raise HTTPException(502, "The AI could not write the report right now. Please try again later.") from exc
        content = clean_content(resp.content) or ""
        if len(content) < 40:
            raise HTTPException(502, "The AI could not write the report right now. Please try again later.")
    report = InsightReport(company_id=company.id if company else None, audience=audience, language=lang,
                           content=content[:20000], metrics=json.loads(json.dumps(metrics, default=str)),
                           created_by=created_by)
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def latest_report(db: Session, company_id: int | None, audience: str) -> InsightReport | None:
    stmt = select(InsightReport).where(InsightReport.audience == audience)
    stmt = stmt.where(InsightReport.company_id == company_id) if company_id else stmt.where(InsightReport.company_id.is_(None))
    return db.scalar(stmt.order_by(InsightReport.id.desc()))
