"""Services of a travel company: what it offers, how each is priced, what the AI must ask the client, which
parts its quotation has and which booking steps follow the payment.

Every company starts with the built-in services below and can change them, add its own (described in its
own words to the AI service builder) or switch them off. The AI reads the active services to take requests.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import workflow as wf
from .branding import clean_text
from .models import Company, Service

PARTS: tuple[str, ...] = ("flight", "hotel", "transport", "activity", "food", "visa", "insurance", "other")
FIELD_TYPES = ("text", "long_text", "number", "date", "choice", "phone", "email")
# Answers with these keys also fill the request's own columns (shown everywhere, used for urgency and search).
STANDARD_FIELDS = ("destination", "origin", "depart_date", "return_date", "adults", "children", "full_name", "phone",
                   "email", "budget")
MAX_FIELDS, MAX_STEPS = 25, 20
KEY = r"^[a-z][a-z0-9_]{1,39}$"


def _line(v: str) -> str:
    return clean_text(v or "", multiline=False)


class FieldDef(BaseModel):
    """One question the AI asks the client for this service."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=KEY)
    label_en: str = Field(min_length=1, max_length=80)
    label_ar: str = Field(min_length=1, max_length=80)
    type: Literal["text", "long_text", "number", "date", "choice", "phone", "email"] = "text"
    required: bool = True
    choices: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("label_en", "label_ar")
    @classmethod
    def one_line(cls, v: str) -> str:
        return _line(v)

    @field_validator("choices")
    @classmethod
    def clean_choices(cls, v: list[str]) -> list[str]:
        return [c for c in (_line(x)[:60] for x in v) if c]


class StepDef(BaseModel):
    """One booking step after the payment (book the flight, send the visa…), ticked by staff."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=KEY)
    label_en: str = Field(min_length=1, max_length=80)
    label_ar: str = Field(min_length=1, max_length=80)

    @field_validator("label_en", "label_ar")
    @classmethod
    def one_line(cls, v: str) -> str:
        return _line(v)


class DocDef(BaseModel):
    """A document the client sends (passport copy, photo, bank statement…), as a photo or PDF."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=KEY)
    label_en: str = Field(min_length=1, max_length=80)
    label_ar: str = Field(min_length=1, max_length=80)
    required: bool = True
    per_traveller: bool = False  # one for each traveller (passports)

    @field_validator("label_en", "label_ar")
    @classmethod
    def one_line(cls, v: str) -> str:
        return _line(v)


class ServiceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name_en: str = Field(min_length=2, max_length=120)
    name_ar: str = Field(min_length=2, max_length=120)
    description_en: str = Field(default="", max_length=2000)
    description_ar: str = Field(default="", max_length=2000)
    pricing: Literal["fixed", "dynamic", "packages"] = "dynamic"
    price: Decimal | None = Field(default=None, ge=0, le=Decimal("100000000"), decimal_places=3)
    price_note: str = Field(default="", max_length=1000)
    parts: list[Literal["flight", "hotel", "transport", "activity", "food", "visa", "insurance", "other"]] = Field(
        default_factory=list, max_length=8)
    fields: list[FieldDef] = Field(default_factory=list, max_length=MAX_FIELDS)
    steps: list[StepDef] = Field(default_factory=list, max_length=MAX_STEPS)
    documents: list[DocDef] = Field(default_factory=list, max_length=15)
    # The steps of its requests (None: the built-in default for this kind of service).
    workflow: list[wf.StepIn] | None = Field(default=None, max_length=wf.MAX_STEPS)
    rules: str = Field(default="", max_length=4000)
    is_active: bool = True

    @field_validator("name_en", "name_ar")
    @classmethod
    def one_line(cls, v: str) -> str:
        return _line(v)

    @field_validator("description_en", "description_ar", "price_note", "rules")
    @classmethod
    def text(cls, v: str) -> str:
        return clean_text(v or "", multiline=True)

    @model_validator(mode="after")
    def consistent(self):
        keys = [f.key for f in self.fields]
        if len(keys) != len(set(keys)):
            raise ValueError("Two questions have the same key")
        if len({s.key for s in self.steps}) != len(self.steps):
            raise ValueError("Two booking steps have the same key")
        if len({d.key for d in self.documents}) != len(self.documents):
            raise ValueError("Two documents have the same key")
        self.parts = [p for p in PARTS if p in self.parts]
        if self.pricing == "fixed" and self.price is None:
            raise ValueError("A fixed-price service needs its price")
        if self.workflow is not None:
            try:
                wf.validate(self.workflow)
            except HTTPException as exc:
                raise ValueError(exc.detail) from None
        return self


class ServiceOut(ServiceIn):
    id: int
    key: str | None
    position: int
    workflow_custom: bool = False  # the owner changed its steps (else the built-in default)


def service_out(s: Service) -> ServiceOut:
    return ServiceOut(id=s.id, key=s.key, position=s.position, name_en=s.name_en, name_ar=s.name_ar,
                      description_en=s.description_en, description_ar=s.description_ar, pricing=s.pricing,
                      price=s.price, price_note=s.price_note, parts=list(s.parts or []),
                      fields=[FieldDef.model_validate(f) for f in s.fields or []],
                      steps=[StepDef.model_validate(x) for x in s.steps or []],
                      documents=[DocDef.model_validate(x) for x in s.documents or []],
                      workflow=[wf.StepIn.model_validate(x) for x in wf.template_for(s)], workflow_custom=bool(s.workflow),
                      rules=s.rules, is_active=s.is_active)


def apply(service: Service, data: ServiceIn) -> None:
    for key, value in data.model_dump(exclude={"workflow"}).items():
        setattr(service, key, value)
    if "workflow" in data.model_fields_set:
        steps = [x.model_dump(mode="json") for x in data.workflow] if data.workflow else None
        service.workflow = None
        # Saving the default as it is keeps the service on the default (it follows later improvements).
        service.workflow = steps if steps and steps != wf.template_for(service) else None


# --- Built-in services --------------------------------------------------------------------------------

def _f(key, en, ar, type_="text", required=True, choices=None) -> dict:
    return {"key": key, "label_en": en, "label_ar": ar, "type": type_, "required": required, "choices": choices or []}


def _s(key, en, ar) -> dict:
    return {"key": key, "label_en": en, "label_ar": ar}


def _d(key, en, ar, required=True, per_traveller=False) -> dict:
    return {"key": key, "label_en": en, "label_ar": ar, "required": required, "per_traveller": per_traveller}


PASSPORT = _d("passport", "Passport copy", "صورة جواز السفر", True, True)


TRAVELLERS = [_f("adults", "Adults", "البالغون", "number"), _f("children", "Children (ages)", "الأطفال (أعمارهم)", required=False)]
CONTACT = [_f("full_name", "Full name", "الاسم الكامل"), _f("phone", "WhatsApp number", "رقم واتساب", "phone")]
DOCS = _s("documents", "Send all travel documents to the client", "إرسال كل وثائق السفر للعميل")

BUILT_IN: list[dict] = [
    {"key": "packages", "name_en": "Holiday packages", "name_ar": "الباقات السياحية", "pricing": "packages",
     "description_en": "Our ready-made trips with fixed prices.", "description_ar": "رحلاتنا الجاهزة بأسعار ثابتة.",
     "parts": [], "fields": [], "steps": [_s("book", "Book the package", "حجز الباقة"), DOCS], "documents": [PASSPORT]},
    {"key": "custom_trip", "name_en": "Tailor-made trip", "name_ar": "رحلة حسب الطلب", "pricing": "dynamic",
     "description_en": "A trip planned around the client: flights, hotels, transport and activities.",
     "description_ar": "رحلة نخططها حول العميل: طيران وفنادق ومواصلات وأنشطة.",
     "parts": ["flight", "hotel", "transport", "activity"],
     "fields": [_f("destination", "Destination", "الوجهة"), _f("origin", "Departure city", "مدينة المغادرة", required=False),
                _f("depart_date", "Departure date", "تاريخ المغادرة", "date"), _f("return_date", "Return date", "تاريخ العودة", "date"),
                *TRAVELLERS, _f("budget", "Budget", "الميزانية", required=False),
                _f("preferences", "Preferences (hotel style, activities…)", "التفضيلات (نوع الفندق، الأنشطة…)", "long_text", False),
                *CONTACT],
     "steps": [_s("flights", "Book the flights", "حجز الطيران"), _s("hotel", "Book the hotels", "حجز الفنادق"),
               _s("transport", "Arrange the transport", "ترتيب المواصلات"), _s("activities", "Book the activities", "حجز الأنشطة"), DOCS],
     "documents": [PASSPORT]},
    {"key": "flights", "name_en": "Flight tickets", "name_ar": "تذاكر الطيران", "pricing": "dynamic", "parts": ["flight"],
     "description_en": "Flight tickets on any airline.", "description_ar": "تذاكر طيران على أي شركة طيران.",
     "fields": [_f("origin", "From", "من"), _f("destination", "To", "إلى"), _f("depart_date", "Departure date", "تاريخ المغادرة", "date"),
                _f("return_date", "Return date (empty for one way)", "تاريخ العودة (فارغ لذهاب فقط)", "date", False), *TRAVELLERS,
                _f("cabin", "Class", "الدرجة", "choice", True, ["Economy", "Premium economy", "Business", "First"]), *CONTACT],
     "steps": [_s("issue", "Issue the tickets", "إصدار التذاكر"), DOCS], "documents": [PASSPORT]},
    {"key": "hotel", "name_en": "Hotel booking", "name_ar": "حجز فندق", "pricing": "dynamic", "parts": ["hotel"],
     "description_en": "Hotels and resorts worldwide.", "description_ar": "فنادق ومنتجعات حول العالم.",
     "fields": [_f("destination", "City", "المدينة"), _f("depart_date", "Check-in", "تاريخ الدخول", "date"),
                _f("return_date", "Check-out", "تاريخ الخروج", "date"), *TRAVELLERS, _f("rooms", "Rooms", "عدد الغرف", "number"),
                _f("budget", "Budget per night", "الميزانية لليلة", required=False), *CONTACT],
     "steps": [_s("book", "Book the hotel", "حجز الفندق"), _s("voucher", "Send the voucher", "إرسال قسيمة الحجز")]},
    {"key": "visa", "name_en": "Visa", "name_ar": "التأشيرات", "pricing": "dynamic", "parts": ["visa"],
     "description_en": "Visa applications for you and your family.", "description_ar": "طلبات التأشيرة لك ولعائلتك.",
     "fields": [_f("destination", "Country", "الدولة"), _f("nationality", "Nationality", "الجنسية"),
                _f("depart_date", "Travel date", "تاريخ السفر", "date"), *TRAVELLERS, *CONTACT],
     "rules": "Passports must be valid for at least 6 months after the travel date.",
     "steps": [_s("docs", "Collect the documents", "جمع المستندات"), _s("submit", "Submit the application", "تقديم الطلب"),
               _s("deliver", "Send the visa to the client", "إرسال التأشيرة للعميل")],
     "documents": [PASSPORT, _d("photo", "Personal photo (white background)", "صورة شخصية (خلفية بيضاء)", True, True),
                   _d("bank_statement", "Bank statement (last 3 months)", "كشف حساب بنكي (آخر 3 أشهر)"),
                   _d("booking", "Flight and hotel bookings", "حجوزات الطيران والفندق", False)]},
    {"key": "embassy", "name_en": "Embassy appointment", "name_ar": "موعد السفارة", "pricing": "dynamic", "parts": ["other"],
     "description_en": "We book your embassy or visa-centre appointment and can go with you.",
     "description_ar": "نحجز موعدك في السفارة أو مركز التأشيرات ويمكننا مرافقتك.",
     "fields": [_f("destination", "Embassy of (country)", "سفارة (الدولة)"), _f("nationality", "Nationality", "الجنسية"),
                _f("purpose", "Purpose (visa, passport, papers…)", "الغرض (تأشيرة، جواز، أوراق…)"),
                _f("preferred_times", "Days and times that suit you", "الأيام والأوقات المناسبة لك", "long_text"),
                _f("impossible_times", "Times that are not possible", "الأوقات غير الممكنة", "long_text", False),
                *TRAVELLERS, *CONTACT],
     "steps": [], "documents": [PASSPORT]},
    {"key": "airport_assist", "name_en": "Airport assistance", "name_ar": "خدمة المساعدة في المطار", "pricing": "dynamic",
     "parts": ["other"],
     "description_en": "Meet and assist at the airport: check-in, passport control, lounge and luggage.",
     "description_ar": "استقبال ومساعدة في المطار: إنهاء إجراءات السفر والجوازات والصالة والأمتعة.",
     "fields": [_f("origin", "Airport", "المطار"), _f("direction", "Arrival or departure", "وصول أو مغادرة", "choice", True,
                                                     ["Arrival", "Departure", "Transit"]),
                _f("depart_date", "Date", "التاريخ", "date"), _f("flight_number", "Flight number", "رقم الرحلة"),
                _f("preferred_times", "Time that suits you", "الوقت المناسب لك", "text", False), *TRAVELLERS, *CONTACT],
     "steps": [], "documents": []},
    {"key": "airport_transfer", "name_en": "Airport transfer", "name_ar": "التوصيل من وإلى المطار", "pricing": "dynamic",
     "parts": ["transport"],
     "description_en": "A private car between the airport and your hotel or home. Can be added to your flights.",
     "description_ar": "سيارة خاصة بين المطار والفندق أو المنزل. يمكن إضافتها إلى رحلتك.",
     "fields": [_f("origin", "Pick-up place", "مكان الاستقبال"), _f("destination", "Drop-off place", "مكان التوصيل"),
                _f("depart_date", "Date", "التاريخ", "date"), _f("preferred_times", "Pick-up time", "وقت الاستقبال"),
                _f("flight_number", "Flight number", "رقم الرحلة", "text", False),
                _f("car", "Car", "السيارة", "choice", False, ["Sedan", "SUV", "Van", "Luxury"]), *TRAVELLERS, *CONTACT],
     "steps": [], "documents": []},
    {"key": "concierge", "name_en": "Special request", "name_ar": "طلب خاص", "pricing": "dynamic", "parts": ["other"],
     "description_en": "Anything beyond our packages: private transfers, restaurants, events, surprises.",
     "description_ar": "أي شيء خارج باقاتنا: تنقلات خاصة، مطاعم، فعاليات، مفاجآت.",
     "fields": [_f("details", "What do you need?", "ماذا تحتاج؟", "long_text"), _f("depart_date", "Date", "التاريخ", "date", False), *CONTACT],
     "steps": [_s("arrange", "Arrange it", "الترتيب"), _s("confirm", "Confirm to the client", "التأكيد للعميل")]},
]


WHEN = _f("depart_date", "Date", "التاريخ", "date")
GUESTS = _f("adults", "Guests", "عدد الضيوف", "number")
BOOK = _s("book", "Book it with the provider", "الحجز مع المزوّد")
CONFIRM = _s("confirm", "Confirm the details to the client", "تأكيد التفاصيل للعميل")

# Given with the "Luxury concierge services" feature; taken back (switched off, not deleted) when it is removed.
CONCIERGE_PACK: list[dict] = [
    {"key": "villa", "name_en": "Private villas & estates", "name_ar": "فلل وقصور خاصة", "pricing": "dynamic", "parts": ["hotel"],
     "description_en": "Private villas, chalets and estates with staff, chosen for privacy and comfort.",
     "description_ar": "فلل وشاليهات وقصور خاصة مع طاقم خدمة، مختارة للخصوصية والراحة.",
     "fields": [_f("destination", "Destination", "الوجهة"), _f("depart_date", "Arrival", "الوصول", "date"),
                _f("return_date", "Departure", "المغادرة", "date"), GUESTS, _f("bedrooms", "Bedrooms", "غرف النوم", "number"),
                _f("preferences", "Wishes (pool, chef, beach…)", "الرغبات (مسبح، طاهٍ، شاطئ…)", "long_text", False), *CONTACT],
     "steps": [BOOK, CONFIRM, DOCS], "documents": [PASSPORT]},
    {"key": "private_jet", "name_en": "Private aviation", "name_ar": "الطيران الخاص", "pricing": "dynamic", "parts": ["flight"],
     "description_en": "Private jets and helicopters, on your schedule.", "description_ar": "طائرات ومروحيات خاصة، في الوقت الذي يناسبك.",
     "fields": [_f("origin", "From", "من"), _f("destination", "To", "إلى"), _f("depart_date", "Departure date", "تاريخ المغادرة", "date"),
                _f("return_date", "Return date (empty for one way)", "تاريخ العودة (فارغ لذهاب فقط)", "date", False), GUESTS,
                _f("preferences", "Times, luggage, pets, catering…", "الأوقات، الأمتعة، الحيوانات الأليفة، الضيافة…", "long_text", False), *CONTACT],
     "steps": [BOOK, CONFIRM, DOCS], "documents": [PASSPORT]},
    {"key": "yacht", "name_en": "Yacht charter", "name_ar": "استئجار يخت", "pricing": "dynamic", "parts": ["activity"],
     "description_en": "Day or week charters with crew.", "description_ar": "رحلات يخت ليوم أو أسبوع مع الطاقم.",
     "fields": [_f("destination", "Where", "المكان"), WHEN, _f("days", "Days", "عدد الأيام", "number"), GUESTS,
                _f("preferences", "Wishes (size, crew, catering…)", "الرغبات (الحجم، الطاقم، الضيافة…)", "long_text", False), *CONTACT],
     "steps": [BOOK, CONFIRM], "documents": [PASSPORT]},
    {"key": "cruise", "name_en": "Luxury cruise", "name_ar": "رحلة بحرية فاخرة", "pricing": "dynamic", "parts": ["activity"],
     "description_en": "Ocean, river and expedition cruises.", "description_ar": "رحلات بحرية في المحيطات والأنهار والرحلات الاستكشافية.",
     "fields": [_f("destination", "Region or route", "المنطقة أو المسار"), WHEN, *TRAVELLERS,
                _f("preferences", "Cabin, cruise line, wishes", "الكابينة، شركة الرحلات، الرغبات", "long_text", False), *CONTACT],
     "steps": [BOOK, CONFIRM, DOCS], "documents": [PASSPORT]},
    {"key": "dining", "name_en": "Dining & nightlife", "name_ar": "المطاعم والسهرات", "pricing": "dynamic", "parts": ["food"],
     "description_en": "Tables at the most sought-after restaurants and venues.", "description_ar": "طاولات في أكثر المطاعم والأماكن طلبًا.",
     "fields": [_f("destination", "City", "المدينة"), WHEN, GUESTS,
                _f("details", "Restaurant, time, occasion", "المطعم، الوقت، المناسبة", "long_text"), *CONTACT],
     "steps": [BOOK, CONFIRM]},
    {"key": "vip_events", "name_en": "VIP access & events", "name_ar": "الدخول المميز والفعاليات", "pricing": "dynamic", "parts": ["activity"],
     "description_en": "Tickets and hospitality for sport, fashion, music and cultural events worldwide.",
     "description_ar": "تذاكر وضيافة لفعاليات الرياضة والأزياء والموسيقى والثقافة حول العالم.",
     "fields": [_f("details", "Event", "الفعالية"), WHEN, GUESTS, *CONTACT], "steps": [BOOK, CONFIRM]},
    {"key": "car_rental", "name_en": "Chauffeur & car rental", "name_ar": "سائق خاص وتأجير سيارات", "pricing": "dynamic", "parts": ["transport"],
     "description_en": "A car with a driver, or a car of your choice to drive.", "description_ar": "سيارة مع سائق، أو سيارة من اختيارك تقودها بنفسك.",
     "fields": [_f("destination", "City", "المدينة"), _f("depart_date", "From", "من تاريخ", "date"), _f("return_date", "Until", "إلى تاريخ", "date"),
                _f("cabin", "Service", "الخدمة", "choice", True, ["With a driver", "Self-drive"]),
                _f("preferences", "Car type", "نوع السيارة", required=False), *CONTACT],
     "steps": [BOOK, CONFIRM], "documents": [_d("licence", "Driving licence (self-drive)", "رخصة القيادة (للقيادة الذاتية)", False)]},
]
PACK_KEYS = {raw["key"] for raw in CONCIERGE_PACK}


def _built_in_for(company: Company) -> list[dict]:
    from .addons import has_addon  # noqa: PLC0415 (addons reads the catalog's company)

    return BUILT_IN + (CONCIERGE_PACK if has_addon(company, "concierge_services") else [])


def sync_pack(db: Session, company: Company) -> None:
    """The luxury services follow the feature: added and switched on with it, switched off without it."""
    from .addons import has_addon  # noqa: PLC0415

    on = has_addon(company, "concierge_services")
    if on:
        ensure_built_in(db, company)
    for service in db.scalars(select(Service).where(Service.company_id == company.id, Service.key.in_(PACK_KEYS))).all():
        service.is_active = on
    db.flush()


def ensure_built_in(db: Session, company: Company) -> None:
    """Gives a company the built-in services it doesn't have yet (never changes the ones it edited)."""
    have = set(db.scalars(select(Service.key).where(Service.company_id == company.id, Service.key.is_not(None))).all())
    for i, raw in enumerate(_built_in_for(company)):
        if raw["key"] in have:
            continue
        data = ServiceIn.model_validate({k: v for k, v in raw.items() if k != "key"})
        service = Service(company_id=company.id, key=raw["key"], position=i)
        apply(service, data)
        db.add(service)
    # Built-in services made before client documents existed get their usual documents once.
    defaults = {raw["key"]: raw.get("documents", []) for raw in BUILT_IN + CONCIERGE_PACK}
    for service in db.scalars(select(Service).where(Service.company_id == company.id, Service.key.is_not(None),
                                                    Service.documents.is_(None))).all():
        service.documents = defaults.get(service.key, [])
    db.flush()


def active_services(db: Session, company_id: int) -> list[Service]:
    return db.scalars(select(Service).where(Service.company_id == company_id, Service.is_active.is_(True))
                      .order_by(Service.position, Service.id)).all()


def service_by_key(db: Session, company_id: int, key: str) -> Service | None:
    return db.scalar(select(Service).where(Service.company_id == company_id, Service.key == key))


# --- Checking a client's answers ----------------------------------------------------------------------

def check_answers(service: Service, answers: dict) -> tuple[dict, list[str]]:
    """Cleans the answers to this service's questions. Returns (answers, missing required labels)."""
    clean, missing = {}, []
    for f in service.fields or []:
        raw = answers.get(f["key"])
        value = clean_text(str(raw), multiline=f["type"] == "long_text")[:1000] if raw not in (None, "") else ""
        if f["type"] == "number" and value:
            m = re.search(r"\d+", value)
            value = m.group(0) if m else ""
        if f["type"] == "date" and value and not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
            value = ""  # the AI must give YYYY-MM-DD
        if value:
            clean[f["key"]] = value
        elif f.get("required"):
            missing.append(f"{f['key']} ({f['label_en']})")
    return clean, missing
