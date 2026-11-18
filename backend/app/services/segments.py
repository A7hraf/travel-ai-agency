"""Learning from the requests the system keeps.

Two audiences, never mixed:

* A company sees its own clients in groups (VIP, frequent, quiet for a year, new, lost after a quotation, travelling
  soon) and, with the predictions level, who usually travels in the coming weeks and what to offer them. Only this
  company's clients and requests are read.
* The platform owner sees the market across every company: where people travel and when, which hotels, airlines
  and activity companies the agencies book most (partners to negotiate with), how quotations turn into bookings and
  why requests are lost. Totals only: no client names, phone numbers or chats.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Company, Customer, RecommendationSignal, Ticket, TicketStatus as T, TripOption
from .customer_portal import PAID, _departure

BOOKED = (*PAID, T.WORKING)
LOST = (T.REJECTED, T.CANCELLED)
QUOTED_ONCE = (T.QUOTED, T.CHANGES, T.CHOSEN, T.FINAL, T.PENDING_PAYMENT, T.IN_PROGRESS, *BOOKED, *LOST)

# key: (English name, Arabic name, what to do, ما العمل) — the level that shows it
SEGMENTS: dict[str, tuple[str, str, str, str, str]] = {
    "vip": ("VIP clients", "عملاء مميزون", "Thank them personally and offer new packages before anyone else.",
            "اشكرهم شخصيًا وقدّم لهم الباقات الجديدة قبل غيرهم.", "segments"),
    "frequent": ("Frequent travellers", "مسافرون دائمون", "Offer a membership or a loyalty gift.",
                 "اعرض عليهم العضوية أو هدية ولاء.", "segments"),
    "upcoming": ("Travelling in the next 30 days", "مسافرون خلال 30 يومًا",
                 "Offer the extras they may need: airport transfer, insurance, activities.",
                 "اعرض الإضافات التي قد يحتاجونها: التوصيل للمطار، التأمين، الأنشطة.", "segments"),
    "new": ("New clients, not booked yet", "عملاء جدد لم يحجزوا بعد", "Follow up kindly and help them choose.",
            "تابع معهم بلطف وساعدهم في الاختيار.", "segments"),
    "lost_quote": ("Lost after a quotation", "خسرناهم بعد عرض السعر",
                   "Ask what did not suit them and send a better option.",
                   "اسألهم عمّا لم يناسبهم وأرسل خيارًا أفضل.", "segments"),
    "dormant": ("Quiet for a year", "لم يتواصلوا منذ سنة", "Send a 'we miss you' offer for their favourite place.",
                "أرسل لهم عرض «اشتقنا لك» لوجهتهم المفضلة.", "segments"),
    "due_again": ("Usually travel in the coming weeks", "يسافرون عادةً في الأسابيع القادمة",
                  "They travelled in this season before: offer their next trip now.",
                  "سافروا في هذا الموسم من قبل: اعرض عليهم رحلتهم القادمة الآن.", "predictions"),
}
LEVELS = ("segments", "predictions", "targeting")
AR_MONTHS = ("يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر")


def _money(v) -> float:
    return float(v or 0)


def _day(v) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    return v if isinstance(v, date) else None


def _favourite(tickets: list[Ticket]) -> str | None:
    places = Counter((t.destination or "").strip() for t in tickets if (t.destination or "").strip())
    return places.most_common(1)[0][0] if places else None


def client_segments(db: Session, company: Company, today: date, levels: list[str] | tuple[str, ...] = ()) -> dict:
    """This company's clients in groups, each with what to do. Business accounts' staff are not clients here."""
    levels = list(levels) or list(LEVELS)
    customers = {c.id: c for c in db.scalars(select(Customer).where(Customer.company_id == company.id,
                                                                     Customer.partner_id.is_(None))).all()}
    tickets = db.scalars(select(Ticket).where(Ticket.company_id == company.id,
                                              Ticket.customer_id.in_(list(customers) or [0]))).all()
    by_customer: dict[int, list[Ticket]] = defaultdict(list)
    for t in tickets:
        by_customer[t.customer_id].append(t)

    spend = {cid: sum(_money(t.total_price) for t in ts if t.status in BOOKED) for cid, ts in by_customer.items()}
    paying = sorted(v for v in spend.values() if v > 0)
    vip_line = paying[int(len(paying) * 0.9)] if len(paying) >= 5 else (paying[-1] if paying else 0)
    out: dict[str, list[dict]] = {k: [] for k, v in SEGMENTS.items() if v[4] in levels}

    for cid, c in customers.items():
        mine = sorted(by_customer.get(cid, []), key=lambda t: t.created_at or datetime.min)
        booked = [t for t in mine if t.status in BOOKED]
        last = mine[-1] if mine else None
        last_day = _day(last.created_at) if last else _day(c.created_at)
        row = {"id": c.id, "name": c.name or (f"+{c.whatsapp_id}" if c.whatsapp_id else "—"), "phone": c.phone,
               "reachable": bool(c.whatsapp_id), "trips": len(booked), "spent": round(spend.get(cid, 0), 3),
               "currency": company.currency, "favourite": _favourite(booked or mine),
               "last_contact": last_day.isoformat() if last_day else None}

        def add(key: str, why: str, why_ar: str) -> None:
            if key in out:
                out[key].append({**row, "why": why, "why_ar": why_ar})

        if booked and spend.get(cid, 0) >= vip_line > 0 and len(booked) >= 2:
            add("vip", f"{len(booked)} trips", f"{len(booked)} رحلات")
        recent = [t for t in booked if (_day(t.created_at) or today) >= today - timedelta(days=730)]
        if len(recent) >= 3:
            add("frequent", f"{len(recent)} trips in 2 years", f"{len(recent)} رحلات في سنتين")
        soon = [d for d in (_departure(t) for t in booked) if d and today <= d <= today + timedelta(days=30)]
        if soon:
            add("upcoming", f"leaves {min(soon).isoformat()}", f"يغادر {min(soon).isoformat()}")
        if not booked and _day(c.created_at) and _day(c.created_at) >= today - timedelta(days=60) and mine:
            add("new", "asked, not booked yet", "سأل ولم يحجز بعد")
        if last and last.status in LOST and (_day(last.created_at) or today) >= today - timedelta(days=180) \
                and last.status in QUOTED_ONCE and (last.total_price or any(o.sent_to_client for o in last.options)):
            reason = (last.cancel_info or {}).get("reason")
            add("lost_quote", reason or ("turned the quotation down" if last.status == T.REJECTED else "cancelled"),
                reason or ("رفض عرض السعر" if last.status == T.REJECTED else "أُلغي"))
        if booked and last_day and last_day < today - timedelta(days=365):
            add("dormant", f"last contact {last_day.isoformat()}", f"آخر تواصل {last_day.isoformat()}")
        if booked and "due_again" in out:
            months = {d.month for d in (_departure(t) for t in booked) if d and d < today}
            window = {(today + timedelta(days=n)).month for n in range(0, 61, 15)}
            open_now = any(t.status not in (*LOST, T.COMPLETED) and (_departure(t) or today) >= today for t in mine)
            if months & window and not open_now:
                hits = sorted(months & window)
                add("due_again", "travelled in " + ", ".join(date(2000, m, 1).strftime("%B") for m in hits),
                    "سافر في " + "، ".join(AR_MONTHS[m - 1] for m in hits))

    for rows in out.values():
        rows.sort(key=lambda r: (-r["spent"], r["name"]))
    return {"segments": [{"key": k, "label_en": SEGMENTS[k][0], "label_ar": SEGMENTS[k][1], "action_en": SEGMENTS[k][2],
                          "action_ar": SEGMENTS[k][3], "count": len(v), "clients": v[:200]} for k, v in out.items()],
            "clients": len(customers), "levels": levels}


def segment_ids(db: Session, company: Company, key: str, today: date) -> set[int]:
    """The clients of one group, for a targeted message."""
    data = client_segments(db, company, today)
    return {c["id"] for s in data["segments"] if s["key"] == key for c in s["clients"]}


# --- The platform owner: the market across every company ----------------------------------------------------------

def _norm(name: str | None) -> str:
    return " ".join((name or "").split()).strip()


def market(db: Session, today: date, days: int = 365) -> dict:
    """Totals across every company, for the platform owner only. No client names, phones or chats."""
    since = datetime.combine(today - timedelta(days=days), datetime.min.time())
    tickets = db.scalars(select(Ticket).where(Ticket.created_at >= since)).all()
    names = dict(db.execute(select(Company.id, Company.name)).all())

    places: dict[str, dict] = {}
    for t in tickets:
        key = _norm(t.destination).title()
        if not key:
            continue
        p = places.setdefault(key, {"destination": key, "requests": 0, "booked": 0, "travellers": 0, "companies": set(),
                                    "value": defaultdict(float)})
        p["requests"] += 1
        p["companies"].add(t.company_id)
        if t.status in BOOKED:
            p["booked"] += 1
            p["travellers"] += (t.adults or 0) + (t.children or 0)
            p["value"][t.currency] += _money(t.total_price)
    destinations = sorted(places.values(), key=lambda p: (-p["requests"], p["destination"]))[:25]
    for p in destinations:
        p["companies"] = len(p["companies"])
        p["value"] = {k: round(v, 3) for k, v in p["value"].items()}
        p["conversion"] = round(p["booked"] / p["requests"], 2) if p["requests"] else None

    months = Counter()
    for t in tickets:
        d = _departure(t)
        if d:
            months[d.strftime("%Y-%m")] += 1
    season = []
    if months:  # every month from the first to the last, so quiet months show as quiet
        y, m = map(int, min(months).split("-"))
        last = max(months)
        while f"{y:04d}-{m:02d}" <= last:
            season.append({"month": f"{y:04d}-{m:02d}", "trips": months.get(f"{y:04d}-{m:02d}", 0)})
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    season = season[-24:]

    options = db.scalars(select(TripOption).where(TripOption.ticket_id.in_([t.id for t in tickets] or [0]),
                                                  TripOption.chosen.is_(True))).all()
    status = {t.id: t.status for t in tickets}
    sellers: dict[tuple[str, str], dict] = {}
    for o in options:
        name = _norm(o.provider)
        if not name or status.get(o.ticket_id) not in BOOKED:
            continue
        s = sellers.setdefault((o.category, name.lower()), {"category": o.category, "provider": name, "bookings": 0,
                                                            "companies": set(), "sold": 0.0, "cost": 0.0})
        s["bookings"] += 1
        s["companies"].add(o.company_id)
        s["sold"] += _money(o.price)
        s["cost"] += _money(o.cost_price)
    partners = []
    for s in sorted(sellers.values(), key=lambda s: (-s["bookings"], -s["sold"]))[:30]:
        s["companies"] = len(s["companies"])
        s["sold"], s["cost"] = round(s["sold"], 3), round(s["cost"], 3)
        s["why"] = ("booked by several agencies: negotiate a platform rate" if s["companies"] >= 2
                    else "a strong supplier of one agency")
        partners.append(s)

    quoted = [t for t in tickets if t.status in QUOTED_ONCE]
    won = [t for t in quoted if t.status in BOOKED]
    reasons = Counter(((t.cancel_info or {}).get("reason")
                       or ("Turned the quotation down" if t.status == T.REJECTED else "Cancelled"))
                      for t in tickets if t.status in LOST)
    windows = [(d - _day(t.created_at)).days for t in tickets if t.status in BOOKED
               for d in [_departure(t)] if d and _day(t.created_at) and d >= _day(t.created_at)]
    signals = Counter((s.event, s.from_ai) for s in db.scalars(
        select(RecommendationSignal).where(RecommendationSignal.created_at >= since)).all())
    ai_suggested, ai_chosen = signals[("suggested", True)], signals[("chosen", True)]
    per_company = Counter(t.company_id for t in tickets)

    return {
        "days": days, "requests": len(tickets), "companies": len(per_company),
        "funnel": {"requests": len(tickets), "quoted": len(quoted), "booked": len(won),
                   "conversion": round(len(won) / len(quoted), 2) if quoted else None},
        "destinations": destinations, "season": season, "partners": partners,
        "lost_reasons": [{"reason": r, "count": n} for r, n in reasons.most_common(10)],
        "booking_window_days": sorted(windows)[len(windows) // 2] if windows else None,
        "ai_learning": {"suggested": ai_suggested, "chosen": ai_chosen,
                        "chosen_rate": round(ai_chosen / ai_suggested, 2) if ai_suggested else None,
                        "team_added": signals[("added", False)]},
        "busiest_companies": [{"company": names.get(cid, "?"), "requests": n} for cid, n in per_company.most_common(10)],
    }
