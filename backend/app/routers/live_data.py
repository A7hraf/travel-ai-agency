"""Live travel data keys and usage.

The platform owner sets the central keys (SerpApi for Google Hotels and Google Flights, Viator for
activities) and may give a company its own key, which that company then uses. Keys are write-only: the API
only says whether one is set. A company sees its searches used and left, never a key.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import platform_settings as ps
from ..addons import Grant, grants
from ..audit import audit
from ..database import get_db
from ..deps import get_company_user, require_system_admin
from ..models import Company, User
from ..services import live_data as svc

router = APIRouter(tags=["live data"])


class KeysIn(BaseModel):
    serpapi_key: str | None = Field(default=None, max_length=200)  # None: unchanged; "": remove
    viator_key: str | None = Field(default=None, max_length=200)


class CompanyKeysIn(KeysIn):
    # While the company pays for its own key, the platform's monthly limit can be lifted.
    unlimited: bool | None = None


def _central() -> dict:
    out = {}
    for provider, (_, setting) in svc.PROVIDERS.items():
        key = (ps.get_effective(setting) or "").strip()
        out[provider] = {"set": bool(key), "account": svc.serpapi_account(key) if key and provider == "serpapi" else None}
    return out


@router.get("/api/system/live-data")
def central(_: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    companies = db.scalars(select(Company).order_by(Company.name)).all()
    rows = []
    for c in companies:
        s = svc.status(db, c)
        rows.append({"id": c.id, "name": c.name, "on": s["on"], "used": s["used"], "limit": s["limit"],
                     "own_serpapi": bool((c.serpapi_key or "").strip()), "own_viator": bool((c.viator_key or "").strip())})
    return {"keys": _central(), "companies": rows}


@router.put("/api/system/live-data")
def save_central(body: KeysIn, me: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    changes = {}
    for field, setting in (("serpapi_key", "serpapi_api_key"), ("viator_key", "viator_api_key")):
        value = svc.clean_key(getattr(body, field))
        if value is not None:
            changes[setting] = value
            old = (ps.get_effective(setting) or "").strip()
            if old:
                svc.forget_account(old)
    if changes:
        ps.save(db, changes, me.email)
        audit(db, me, "live_data.central_keys", detail=", ".join(f"{k}: {'set' if v else 'removed'}" for k, v in changes.items()),
              commit=True)
    return {"keys": _central()}


@router.post("/api/system/live-data/test")
def test_central(_: User = Depends(require_system_admin)):
    """Tries the central keys now and says what each provider answered."""
    return svc.test_keys(central=True)


@router.post("/api/system/companies/{company_id}/live-data/test")
def test_company(company_id: int, _: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    return svc.test_keys(_company(db, company_id), central=False)


def _company(db: Session, company_id: int) -> Company:
    c = db.get(Company, company_id)
    if c is None:
        raise HTTPException(404, "Company not found")
    return c


def _company_view(db: Session, c: Company) -> dict:
    s = svc.status(db, c)
    own = (c.serpapi_key or "").strip()
    return {**s, "own_serpapi": bool(own), "own_viator": bool((c.viator_key or "").strip()),
            "own_account": svc.serpapi_account(own) if own else None}


@router.get("/api/system/companies/{company_id}/live-data")
def company_keys(company_id: int, _: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    return _company_view(db, _company(db, company_id))


@router.put("/api/system/companies/{company_id}/live-data")
def save_company_keys(company_id: int, body: CompanyKeysIn, me: User = Depends(require_system_admin),
                      db: Session = Depends(get_db)):
    c = _company(db, company_id)
    said = []
    for field in ("serpapi_key", "viator_key"):
        value = svc.clean_key(getattr(body, field))
        if value is not None:
            if getattr(c, field):
                svc.forget_account(getattr(c, field))
            setattr(c, field, value or None)
            said.append(f"{field}: {'set' if value else 'removed'}")
    if body.unlimited is not None:
        g = grants(c)["live_search"]
        current = c.addons if isinstance(c.addons, dict) else {}
        limit = None if body.unlimited else (g.limit or 20)
        c.addons = {**current, "live_search": Grant(**{**g.model_dump(), "on": True, "limit": limit}).model_dump(mode="json")}
        said.append("no monthly limit" if body.unlimited else f"limit {limit} a month")
    if said:
        audit(db, me, "live_data.company_keys", target=c.name, company_id=c.id, detail=", ".join(said))
    db.commit()
    return _company_view(db, c)


@router.get("/api/live-data")
def my_usage(me: User = Depends(get_company_user), db: Session = Depends(get_db)):
    """Searches used and left this month, and whether the company uses its own key or the platform's."""
    return svc.status(db, me.company)
