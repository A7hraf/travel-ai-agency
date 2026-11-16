import json
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..addons import use
from ..ai.llm import LLMError, MockTravelLLM, get_llm_client
from ..audit import audit
from ..branding import clean_text
from ..ratelimit import limiter
from ..database import get_db
from ..deps import require_permission
from ..models import Ticket, TravelPackage, User
from ..schemas import PackageIn, PackageOut
from ..services import plans, seats
from ..timeutil import local_today
from .media import media_belongs_to

router = APIRouter(prefix="/api/packages", tags=["packages"])


def _apply(pkg: TravelPackage, body: PackageIn, default_currency: str, db: Session | None = None) -> None:
    if db is not None and not media_belongs_to(db, body.image_url, pkg.company_id):
        raise HTTPException(400, "Use a photo uploaded by your company")
    data = body.model_dump(exclude={"seats_loaded"})
    # The edit form sends the seat count it loaded. If the employee did not change it, keep the current
    # count (another employee may have changed it while the form was open). It is the number of seats of
    # each departure date; bookings never change it (see services/seats.py).
    if pkg.id is not None and "seats_loaded" in body.model_fields_set and body.seats_available == body.seats_loaded:
        data.pop("seats_available")
    data["currency"] = (data.get("currency") or default_currency).upper()
    # Past departure dates can't be sold any more: they are dropped.
    today = local_today()
    data["departure_dates"] = sorted({d.isoformat() for d in body.departure_dates if d >= today})
    if body.departure_dates and not data["departure_dates"]:
        raise HTTPException(400, "All the departure dates are in the past. Add a future date, "
                                 "or remove every date for flexible dates on request.")
    data["includes"] = [s.strip() for s in body.includes if s.strip()]
    data["excludes"] = [s.strip() for s in body.excludes if s.strip()]
    data["tags"] = [s.strip().lower() for s in body.tags if s.strip()]
    for key, value in data.items():
        setattr(pkg, key, value)


def _check_not_below_bookings(db: Session, pkg: TravelPackage) -> None:
    """Fewer seats per date than are already booked on a date would oversell it (and the extra customers
    would only find out at the airport): refuse, and say how many seats are taken."""
    if pkg.seats_available is None:
        return
    held = seats.held_by_date(db, pkg.id)
    over = sorted((d, n) for d, n in held.items() if n > pkg.seats_available and d >= local_today().isoformat())
    if over:
        day, booked = max(over, key=lambda dn: dn[1])
        db.rollback()
        raise HTTPException(400, f"{booked} seats are already booked on {day}. Set at least {booked} seats per "
                                 "date, or cancel bookings first.")


def _with_seats(db: Session, pkg: TravelPackage) -> TravelPackage:
    """Adds the seats left on each upcoming departure date (seats_left_by_date) for the response."""
    today = local_today().isoformat()
    seats.left_by_date(db, pkg, [d for d in pkg.departure_dates or [] if d >= today], today)
    return pkg


def _get(db: Session, me: User, package_id: int) -> TravelPackage:
    pkg = db.get(TravelPackage, package_id)
    if pkg is None or pkg.company_id != me.company_id:
        raise HTTPException(404, "Package not found")
    return pkg


@router.get("", response_model=list[PackageOut])
def list_packages(me: User = Depends(require_permission("packages.view")), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(TravelPackage).where(TravelPackage.company_id == me.company_id).order_by(TravelPackage.id.desc())
    ).all()
    return [_with_seats(db, p) for p in rows]


@router.get("/{package_id}", response_model=PackageOut)
def get_package(package_id: int, me: User = Depends(require_permission("packages.view")),
                db: Session = Depends(get_db)):
    return _with_seats(db, _get(db, me, package_id))


@router.post("", response_model=PackageOut, status_code=201)
def create_package(body: PackageIn, me: User = Depends(require_permission("packages.manage")),
                   db: Session = Depends(get_db)):
    if body.is_active:
        plans.check_package_limit(db, me.company_id)
    pkg = TravelPackage(company_id=me.company_id)
    _apply(pkg, body, me.company.currency, db)
    db.add(pkg)
    audit(db, me, "package.created", target=pkg.title)
    db.commit()
    db.refresh(pkg)
    return _with_seats(db, pkg)


@router.put("/{package_id}", response_model=PackageOut)
def update_package(package_id: int, body: PackageIn, me: User = Depends(require_permission("packages.manage")),
                   db: Session = Depends(get_db)):
    pkg = _get(db, me, package_id)
    if body.is_active and not pkg.is_active:  # a hidden package shown again counts again
        plans.check_package_limit(db, me.company_id)
    _apply(pkg, body, me.company.currency, db)
    _check_not_below_bookings(db, pkg)
    audit(db, me, "package.updated", target=pkg.title)
    db.commit()
    db.refresh(pkg)
    return _with_seats(db, pkg)


@router.delete("/{package_id}", status_code=204)
def delete_package(package_id: int, me: User = Depends(require_permission("packages.manage")),
                   db: Session = Depends(get_db)):
    pkg = _get(db, me, package_id)
    if db.scalar(select(Ticket.id).where(Ticket.package_id == pkg.id).limit(1)):
        # Keep the history of booked packages; hide it from customers instead.
        pkg.is_active = False
        audit(db, me, "package.hidden", target=pkg.title)
    else:
        audit(db, me, "package.deleted", target=pkg.title)
        db.delete(pkg)
    db.commit()


# --- AI package creator ------------------------------------------------------------------------------------

class PackageIdea(BaseModel):
    text: str = Field(min_length=10, max_length=6000)


CREATOR = """You turn a travel agency owner's notes about ONE trip or experience into a package for their website \
and their AI consultant. Answer with JSON only:
{{"title": "...", "destination": "city or region", "country": "...", "description": "3 to 6 appealing sentences",
 "duration_days": number, "price_per_person": number (in {currency}; 0 if not given), "child_price": number or null,
 "includes": ["..."], "excludes": ["..."], "tags": ["family", "honeymoon", "beach", "adventure", "umrah", "city", ...],
 "hotel_name": "..." or null, "hotel_stars": 1-7 or null, "kind": "trip" or "experience",
 "price_mode": "shown" or "on_request" (on_request when the price depends on the client or is not given),
 "departure_dates": ["YYYY-MM-DD", ...] (only dates in the notes, after {today})}}
An experience is one event or activity (a match, a race, diving, a concert). Use only what the notes say; never \
invent prices or dates."""


def _mock_package(text: str) -> dict:
    first = " ".join(re.split(r"[\n,.،]", text.strip())[0].split())[:120] or "New package"
    days = re.search(r"(\d{1,3})\s*(?:days|day|nights|أيام|ليال)", text, re.I)
    price = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*(?:OMR|ريال|ر\.ع)", text, re.I)
    words = text.lower()
    experience = any(w in words for w in ("match", "formula", "race", "concert", "diving", "dive", "مباراة", "سباق", "غوص"))
    return {"title": first, "destination": "", "country": "", "description": " ".join(text.split())[:800],
            "duration_days": int(days.group(1)) if days else 3,
            "price_per_person": float(price.group(1).replace(",", "")) if price else 0,
            "kind": "experience" if experience else "trip", "price_mode": "shown" if price else "on_request",
            "includes": [], "excludes": [], "tags": []}


@router.post("/ai-draft")
def ai_package(body: PackageIdea, me: User = Depends(require_permission("packages.manage")), db: Session = Depends(get_db)):
    """A draft package from the owner's notes. Nothing is saved: the form opens with it to check and save."""
    use(db, me, "package_builder")
    db.commit()
    limiter.check(f"package-builder:{me.company_id}", 20, "The AI is busy: please try again in a few minutes", window=3600)
    llm = get_llm_client()
    if isinstance(llm, MockTravelLLM):
        raw = _mock_package(body.text)
    else:
        prompt = CREATOR.format(currency=me.company.currency or "OMR", today=local_today().isoformat())
        try:
            resp = llm.chat([{"role": "system", "content": prompt}, {"role": "user", "content": body.text}], [])
        except LLMError as exc:
            raise HTTPException(502, "The AI could not create the package right now. Please try again.") from exc
        match = re.search(r"\{.*\}", resp.content or "", re.DOTALL)
        try:
            raw = json.loads(match.group(0)) if match else {}
        except json.JSONDecodeError:
            raw = {}
    raw = raw if isinstance(raw, dict) else {}
    today = local_today().isoformat()
    out = {
        "title": clean_text(str(raw.get("title") or ""), multiline=False)[:200] or "New package",
        "destination": clean_text(str(raw.get("destination") or ""), multiline=False)[:120],
        "country": clean_text(str(raw.get("country") or ""), multiline=False)[:120],
        "description": clean_text(str(raw.get("description") or ""), multiline=True)[:10000],
        "duration_days": min(max(int(raw.get("duration_days") or 1) if str(raw.get("duration_days") or "").isdigit() else 1, 1), 365),
        "price_per_person": max(float(raw.get("price_per_person") or 0), 0) if isinstance(raw.get("price_per_person"), (int, float)) else 0,
        "child_price": raw.get("child_price") if isinstance(raw.get("child_price"), (int, float)) and raw["child_price"] >= 0 else None,
        "includes": [clean_text(str(x), multiline=False)[:200] for x in raw.get("includes") or [] if str(x).strip()][:20],
        "excludes": [clean_text(str(x), multiline=False)[:200] for x in raw.get("excludes") or [] if str(x).strip()][:20],
        "tags": [clean_text(str(x), multiline=False)[:40].lower() for x in raw.get("tags") or [] if str(x).strip()][:10],
        "hotel_name": clean_text(str(raw.get("hotel_name") or ""), multiline=False)[:200] or None,
        "hotel_stars": raw.get("hotel_stars") if isinstance(raw.get("hotel_stars"), int) and 1 <= raw["hotel_stars"] <= 7 else None,
        "kind": raw.get("kind") if raw.get("kind") in ("trip", "experience") else "trip",
        "price_mode": raw.get("price_mode") if raw.get("price_mode") in ("shown", "on_request") else "shown",
        "departure_dates": sorted({d for d in raw.get("departure_dates") or []
                                   if isinstance(d, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) and d > today})[:50],
    }
    if not out["price_per_person"]:
        out["price_mode"] = "on_request"
    return out
