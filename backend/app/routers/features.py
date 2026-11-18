"""Features and AI capabilities of a company.

* ``/api/system/companies/{id}/features``: the platform owner gives features, limits, employee seats and prices.
* ``/api/features``: the company sees what it has and how much it used; its admin chooses which employees use
  the features that count employees.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..addons import FEATURES, Grant, grants, usage
from ..audit import audit
from ..catalog import sync_pack
from ..database import get_db
from ..deps import get_current_user, require_permission, require_system_admin
from ..models import Company, Role, User

router = APIRouter(tags=["features"])


def catalog() -> list[dict]:
    return [{"key": k, "label": f.label, "kind": f.kind, "parent": f.parent, "metered": f.metered, "levels": list(f.levels)}
            for k, f in FEATURES.items()]


def _state(db: Session, company: Company) -> dict:
    g = grants(company)
    seats = {}
    staff = db.scalars(select(User).where(User.company_id == company.id, User.partner_id.is_(None), User.is_active.is_(True))).all()
    for key, grant in g.items():
        if grant.seats is not None:
            seats[key] = [u.id for u in staff if key in (u.ai_features or [])]
    return {"catalog": catalog(), "grants": {k: v.model_dump(mode="json") for k, v in g.items()},
            "usage": {k: usage(db, company.id, k, v) for k, v in g.items() if FEATURES[k].metered and v.on},
            "seats": seats}


def _company(db: Session, company_id: int) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "Company not found")
    return company


@router.get("/api/system/companies/{company_id}/features")
def get_features(company_id: int, _: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    return _state(db, _company(db, company_id))


@router.put("/api/system/companies/{company_id}/features")
def save_features(company_id: int, body: dict[str, Grant], me: User = Depends(require_system_admin),
                  db: Session = Depends(get_db)):
    company = _company(db, company_id)
    unknown = set(body) - set(FEATURES)
    if unknown:
        raise HTTPException(422, f"Unknown feature: {', '.join(sorted(unknown))}")
    for key, g in body.items():
        wrong = set(g.levels) - set(FEATURES[key].levels)
        if wrong:
            raise HTTPException(422, f"{key} has no level {', '.join(sorted(wrong))}")
    current = grants(company)
    pack_was = current["concierge_services"].on
    current.update(body)
    company.addons = {k: v.model_dump(mode="json") for k, v in current.items()}
    # Employees beyond a new, smaller number of seats lose the feature.
    for key, g in current.items():
        if g.seats is not None:
            holders = [u for u in db.scalars(select(User).where(User.company_id == company.id)).all() if key in (u.ai_features or [])]
            for u in holders[g.seats:]:
                u.ai_features = [x for x in u.ai_features if x != key]
    if current["concierge_services"].on != pack_was:
        sync_pack(db, company)
    audit(db, me, "features.saved", target=company.name, company_id=company.id,
          detail=", ".join(f"{k}{'' if v.limit is None else f' ({v.limit}/{v.period})'}" for k, v in current.items() if v.on) or "none")
    db.commit()
    return _state(db, company)


@router.get("/api/features")
def my_features(me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if me.company_id is None or me.partner_id is not None:
        raise HTTPException(403, "Only travel company staff have company features")
    out = _state(db, me.company)
    out["grants"] = {k: v for k, v in out["grants"].items() if v["on"]}
    if me.role != Role.COMPANY_ADMIN:
        out.pop("seats")
    return out


class SeatsIn(BaseModel):
    features: list[str] = Field(default_factory=list, max_length=len(FEATURES))


@router.put("/api/team/{user_id}/features")
def give_features(user_id: int, body: SeatsIn, me: User = Depends(require_permission("users.manage")),
                  db: Session = Depends(get_db)):
    """The company admin chooses which employees use the features that count employees."""
    person = db.get(User, user_id)
    if person is None or person.company_id != me.company_id or person.partner_id is not None:
        raise HTTPException(404, "Team member not found")
    g = grants(me.company)
    wanted = set(body.features)
    for key in wanted:
        if key not in g or not g[key].on or g[key].seats is None:
            raise HTTPException(422, "This feature is not given per employee")
        holders = db.scalars(select(User).where(User.company_id == me.company_id, User.id != person.id)).all()
        if key not in (person.ai_features or []) and sum(key in (u.ai_features or []) for u in holders) >= g[key].seats:
            raise HTTPException(409, f"All {g[key].seats} places for this feature are taken")
    person.ai_features = sorted(wanted) or None
    audit(db, me, "user.features", target=person.email, detail=", ".join(sorted(wanted)) or "none")
    db.commit()
    return {"features": person.ai_features or []}
