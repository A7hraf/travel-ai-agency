"""Branded quotations: the draft (the choices sent) and the final quotation (the client's choices and total), as a
printable page with the company's logo, colours, introduction, photos and terms. The browser saves it as PDF.

The design (introduction, terms, footer) is set once by the owner, or drafted by the AI from a sample quotation
the owner pastes. The data is the request's: it changes every time, the theme stays the same.
"""

from __future__ import annotations

import json
import re
from datetime import timedelta

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ..ai.llm import LLMError, MockTravelLLM, get_llm_client
from ..branding import clean_text, public_branding
from ..models import Company, Supplier, Ticket, TicketStatus as T
from ..timeutil import local_today
from .request_desk import apply_dates_hint
from ..trip_schemas import CATEGORIES

AFTER_FINAL = (T.FINAL, T.PENDING_PAYMENT, T.IN_PROGRESS, T.PAID, T.CONFIRMED)
SHOWS_CHOICES = (T.QUOTED, T.CHANGES, T.CHOSEN)


class QuoteSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    intro_en: str = Field(default="", max_length=3000)
    intro_ar: str = Field(default="", max_length=3000)
    terms_en: str = Field(default="", max_length=4000)
    terms_ar: str = Field(default="", max_length=4000)
    footer_en: str = Field(default="", max_length=500)
    footer_ar: str = Field(default="", max_length=500)
    valid_days: int = Field(default=7, ge=1, le=90)

    def cleaned(self) -> QuoteSettings:
        return QuoteSettings(**{k: clean_text(v, multiline=True) if isinstance(v, str) else v
                                for k, v in self.model_dump().items()})


def settings_of(company: Company) -> QuoteSettings:
    try:
        return QuoteSettings.model_validate(company.quote_settings or {})
    except ValueError:
        return QuoteSettings()


def quotation(db: Session, company: Company, ticket: Ticket, kind: str) -> dict:
    """What the quotation page shows. Never costs, AI estimates, notes or staff."""
    if kind == "final":
        options = [o for o in ticket.options if o.chosen]
        if not options and ticket.service and ticket.service.pricing != "fixed":
            raise HTTPException(409, "There is no final quotation yet: the client hasn't chosen")
    else:
        options = [o for o in ticket.options if o.sent_to_client] or [o for o in ticket.options if o.price is not None]
        if not options:
            raise HTTPException(409, "Add choices with a client price first")
    suppliers = {s.id: s for s in db.query(Supplier).filter(
        Supplier.company_id == company.id, Supplier.id.in_([o.supplier_id for o in options if o.supplier_id])).all()}
    order = {c: i for i, c in enumerate(CATEGORIES)}
    items = []
    for o in sorted(options, key=lambda o: (order.get(o.category, 99), o.position, o.id)):
        s = suppliers.get(o.supplier_id) if o.supplier_id else None
        items.append({"part": o.category, "title": o.title, "provider": o.provider, "link": o.link,
                      "details": o.details or (s.description if s else None) or None,
                      "image_url": o.image_url or (s.image_url if s else None),
                      "stars": s.stars if s and s.category == "hotel" else None,
                      "price": float(o.price) if o.price is not None else None, "chosen": o.chosen})
    b = public_branding(company)
    s = settings_of(company)
    issued = local_today()
    return {
        "kind": kind, "reference": ticket.reference, "title": ticket.package_title, "status": ticket.status,
        "service_en": ticket.service.name_en if ticket.service else None,
        "service_ar": ticket.service.name_ar if ticket.service else None,
        "client": ticket.lead_traveler_name or ticket.customer.name or "",
        "destination": ticket.destination, "origin": ticket.origin, "depart": ticket.departure_date,
        "return": ticket.return_date, "adults": ticket.adults, "children": ticket.children,
        "items": items, "currency": ticket.currency,
        "total": float(ticket.total_price) if kind == "final" and ticket.total_price else None,
        "issued_at": issued, "valid_until": issued + timedelta(days=s.valid_days),
        "company": {"name": company.name, "logo": b.logo, "primary": b.primary_color, "accent": b.accent_color,
                    "email": company.contact_email, "phone": company.contact_phone,
                    "whatsapp": company.whatsapp_display_number},
        "design": s.model_dump(),
        "itinerary": apply_dates_hint(ticket.departure_date, ticket.itinerary or []),
    }


def kind_for_client(ticket: Ticket) -> str | None:
    if ticket.status in AFTER_FINAL:
        return "final"
    if ticket.status in SHOWS_CHOICES:
        return "draft"
    return None


BUILDER = """You read a travel agency's sample quotation and keep only its fixed text, to be reused in every \
quotation: the introduction about the agency, the terms and conditions (payment, cancellation, validity) and the \
footer (contacts, licence). Drop anything about one client or one trip (names, dates, hotels, prices). Answer with \
JSON only: {"intro_en": "...", "intro_ar": "...", "terms_en": "...", "terms_ar": "...", "footer_en": "...", \
"footer_ar": "..."}. Write both languages (Gulf-friendly Modern Standard Arabic); keep the agency's own wording."""


def ai_draft(text: str, current: QuoteSettings) -> QuoteSettings:
    llm = get_llm_client()
    if isinstance(llm, MockTravelLLM):
        paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        terms = [p for p in paras if re.search(r"term|condition|cancel|refund|payment|الشروط|الإلغاء|الدفع", p, re.I)]
        intro = [p for p in paras if p not in terms]
        return QuoteSettings(**{**current.model_dump(), "intro_en": (intro[0] if intro else "")[:3000],
                                "terms_en": "\n\n".join(terms)[:4000]}).cleaned()
    try:
        resp = llm.chat([{"role": "system", "content": BUILDER}, {"role": "user", "content": text[:12000]}], [])
    except LLMError as exc:
        raise HTTPException(502, "The AI could not read the sample right now. Please try again.") from exc
    match = re.search(r"\{.*\}", resp.content or "", re.DOTALL)
    try:
        raw = json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        raw = {}
    raw = {k: str(v)[:4000] for k, v in (raw if isinstance(raw, dict) else {}).items() if k in QuoteSettings.model_fields and k != "valid_days"}
    return QuoteSettings(**{**current.model_dump(), **raw}).cleaned()
