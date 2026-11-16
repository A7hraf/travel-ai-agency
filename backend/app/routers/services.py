"""The company's services (``/api/services``): list, change, add, switch off, and the AI service builder that
turns the owner's own words into a service. Also how clients pay (``/api/payment-info``)."""

import json
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import workflow as wf
from ..ai.llm import LLMError, MockTravelLLM, get_llm_client
from ..addons import use
from ..audit import audit
from ..branding import clean_text
from ..catalog import PARTS, ServiceIn, ServiceOut, apply, ensure_built_in, service_out
from ..database import get_db
from ..deps import get_company_user, require_permission
from ..models import Service, Ticket, User
from ..ratelimit import limiter

router = APIRouter(prefix="/api/services", tags=["services"])
payment_router = APIRouter(prefix="/api/payment-info", tags=["services"])
manager = require_permission("settings.manage")


def _get(db: Session, me: User, service_id: int) -> Service:
    service = db.get(Service, service_id)
    if service is None or service.company_id != me.company_id:
        raise HTTPException(404, "Service not found")
    return service


@router.get("", response_model=list[ServiceOut])
def list_services(me: User = Depends(get_company_user), db: Session = Depends(get_db)):
    ensure_built_in(db, me.company)
    db.commit()
    rows = db.scalars(select(Service).where(Service.company_id == me.company_id).order_by(Service.position, Service.id)).all()
    return [service_out(s) for s in rows]


@router.post("", response_model=ServiceOut, status_code=201)
def create_service(body: ServiceIn, me: User = Depends(manager), db: Session = Depends(get_db)):
    if body.pricing == "packages":
        raise HTTPException(422, "Ready-made packages are one built-in service")
    count = len(db.scalars(select(Service.id).where(Service.company_id == me.company_id)).all())
    if count >= 50:
        raise HTTPException(409, "A company can have at most 50 services")
    service = Service(company_id=me.company_id, position=count)
    apply(service, body)
    db.add(service)
    audit(db, me, "service.created", target=body.name_en)
    db.commit()
    db.refresh(service)
    return service_out(service)


@router.put("/{service_id}", response_model=ServiceOut)
def update_service(service_id: int, body: ServiceIn, me: User = Depends(manager), db: Session = Depends(get_db)):
    service = _get(db, me, service_id)
    if (service.pricing == "packages") != (body.pricing == "packages"):
        raise HTTPException(422, "Only the built-in packages service works with ready-made packages")
    apply(service, body)
    audit(db, me, "service.updated", target=body.name_en)
    db.commit()
    db.refresh(service)
    return service_out(service)


@router.delete("/{service_id}", status_code=204)
def delete_service(service_id: int, me: User = Depends(manager), db: Session = Depends(get_db)):
    service = _get(db, me, service_id)
    if service.key is not None or db.scalar(select(Ticket.id).where(Ticket.service_id == service.id).limit(1)):
        raise HTTPException(409, "Built-in services and services with requests can't be deleted: switch them off instead")
    audit(db, me, "service.deleted", target=service.name_en)
    db.delete(service)
    db.commit()


# --- AI service builder ---------------------------------------------------------------------------------

class DescribeIn(BaseModel):
    text: str = Field(min_length=10, max_length=6000)


BUILDER = """You turn a travel agency owner's description of ONE of their services into a structured service for \
their AI consultant and staff. Answer with JSON only, in this shape:
{{"name_en": "...", "name_ar": "...", "description_en": "...", "description_ar": "...",
 "pricing": "fixed" or "dynamic", "price": number or null (fixed only, in {currency}),
 "price_note": "how the price is set, in English",
 "parts": subset of {parts} (what the quotation contains),
 "fields": [{{"key": "snake_case", "label_en": "...", "label_ar": "...", "type": one of text|long_text|number|date|choice|phone|email,
   "required": true/false, "choices": []}}],
 "steps": [{{"key": "snake_case", "label_en": "...", "label_ar": "..."}}] (the booking checklist),
 "documents": [{{"key": "snake_case", "label_en": "...", "label_ar": "...", "required": true/false, "per_traveller": true/false}}]
   (papers the client must send, like a passport copy),
 "workflow": [{{"key": "snake_case", "type": one of {types}, "label_en": "...", "label_ar": "...",
   "pay_mode": "percent"|"fixed"|"rest" (payment steps only), "pay_value": number or null}}]
   (the request's process in order: start with intake then review; quote when the price depends on the request;
   documents when papers are needed; schedule for an appointment; one or more payment steps, the last one "rest";
   then booking, delivery, trip and feedback as they apply),
 "rules": "conditions and exceptions, in English"}}
Use these keys when they apply: destination, origin, depart_date, return_date, adults, children, budget, full_name, \
phone, email. Always ask full_name and phone. Arabic: Gulf-friendly Modern Standard Arabic."""


def _mock_service(text: str) -> dict:
    first = clean_text(text.split("\n")[0], multiline=False)[:80] or "New service"
    return {"name_en": first, "name_ar": first, "description_en": clean_text(text, multiline=True)[:500],
            "description_ar": "", "pricing": "dynamic", "price": None, "price_note": "", "parts": ["other"],
            "fields": [{"key": "details", "label_en": "What do you need?", "label_ar": "ماذا تحتاج؟", "type": "long_text",
                        "required": True, "choices": []},
                       {"key": "full_name", "label_en": "Full name", "label_ar": "الاسم الكامل", "type": "text",
                        "required": True, "choices": []},
                       {"key": "phone", "label_en": "WhatsApp number", "label_ar": "رقم واتساب", "type": "phone",
                        "required": True, "choices": []}],
            "steps": [{"key": "arrange", "label_en": "Arrange it", "label_ar": "الترتيب"}], "rules": "",
            "workflow": wf.GENERIC}


@router.post("/ai-draft", response_model=ServiceIn)
def ai_build(body: DescribeIn, me: User = Depends(manager), db: Session = Depends(get_db)):
    """A draft service from the owner's words. Nothing is saved: the owner checks it, then saves it."""
    use(db, me, "service_builder")
    db.commit()
    limiter.check(f"service-builder:{me.company_id}", 20, "The AI is busy: please try again in a few minutes", window=3600)
    llm = get_llm_client()
    if isinstance(llm, MockTravelLLM):
        raw = _mock_service(body.text)
    else:
        try:
            resp = llm.chat([{"role": "system", "content": BUILDER.format(currency=me.company.currency or "OMR",
                                                                         parts=list(PARTS), types="|".join(wf.TYPES))},
                             {"role": "user", "content": body.text}], [])
        except LLMError as exc:
            raise HTTPException(502, "The AI could not build the service right now. Please try again.") from exc
        match = re.search(r"\{.*\}", resp.content or "", re.DOTALL)
        try:
            raw = json.loads(match.group(0)) if match else {}
        except json.JSONDecodeError:
            raw = {}
    # Keep what is valid, drop the rest (the owner reviews everything before saving).
    raw = raw if isinstance(raw, dict) else {}
    raw["fields"] = [f for f in raw.get("fields") or [] if isinstance(f, dict)]
    raw["steps"] = [s for s in raw.get("steps") or [] if isinstance(s, dict)]
    raw["documents"] = [d for d in raw.get("documents") or [] if isinstance(d, dict)]
    if not isinstance(raw.get("workflow"), list) or not raw["workflow"]:
        raw.pop("workflow", None)
    raw["parts"] = [p for p in raw.get("parts") or [] if p in PARTS]
    if raw.get("pricing") not in ("fixed", "dynamic"):
        raw["pricing"] = "dynamic"
    allowed = set(ServiceIn.model_fields)
    for _ in range(3):
        try:
            return ServiceIn.model_validate({k: v for k, v in raw.items() if k in allowed})
        except ValidationError as exc:
            for err in exc.errors():
                loc = err.get("loc", ())
                if not loc or loc[0] == "workflow":
                    raw.pop("workflow", None)  # a process that doesn't hold together: the default is used
                elif loc[0] in ("fields", "steps", "documents") and len(loc) > 1 and isinstance(loc[1], int):
                    raw[loc[0]][loc[1]] = None
                elif loc and loc[0] == "price":
                    raw["price"], raw["pricing"] = None, "dynamic"
                elif loc:
                    raw.pop(loc[0], None)
            raw["fields"] = [f for f in raw.get("fields", []) if f]
            raw["steps"] = [s for s in raw.get("steps", []) if s]
            raw["documents"] = [d for d in raw.get("documents", []) if d]
    raise HTTPException(502, "The AI could not build the service right now. Please try again.")


# --- How clients pay -------------------------------------------------------------------------------------

class PaymentInfo(BaseModel):
    en: str = Field(default="", max_length=1500)
    ar: str = Field(default="", max_length=1500)


@payment_router.get("", response_model=PaymentInfo)
def get_payment_info(me: User = Depends(get_company_user)):
    return PaymentInfo.model_validate(me.company.payment_info or {})


@payment_router.put("", response_model=PaymentInfo)
def save_payment_info(body: PaymentInfo, me: User = Depends(manager), db: Session = Depends(get_db)):
    info = PaymentInfo(en=clean_text(body.en, multiline=True), ar=clean_text(body.ar, multiline=True))
    me.company.payment_info = info.model_dump()
    audit(db, me, "payment_info.saved")
    db.commit()
    return info
