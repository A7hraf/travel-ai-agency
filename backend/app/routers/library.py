"""The supplier library (``/api/library``): saved hotels, airlines, transport and activities, the spending figures
and the usual margins. A feature the platform owner switches on per company (with its parts)."""

from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..addons import require_addon
from ..audit import audit
from ..branding import clean_text
from ..database import get_db
from ..deps import require_permission
from ..models import Supplier, TripOption, User
from ..routers.media import media_belongs_to
from ..services import library as svc

router = APIRouter(prefix="/api/library", tags=["library"])
Part = Literal["flight", "hotel", "transport", "activity", "food", "visa", "insurance", "other"]


def viewer(me: User = Depends(require_permission("tickets.view"))) -> User:
    require_addon(me.company, "library")
    return me


def editor(me: User = Depends(require_permission("tickets.manage"))) -> User:
    require_addon(me.company, "library")
    return me


class SupplierIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Part
    name: str = Field(min_length=2, max_length=200)
    place: str = Field(default="", max_length=120)
    stars: int | None = Field(default=None, ge=1, le=7)
    link: str | None = Field(default=None, max_length=500)
    image_url: str | None = Field(default=None, max_length=500)
    description: str = Field(default="", max_length=2000)
    notes: str = Field(default="", max_length=2000)
    usual_cost: Decimal | None = Field(default=None, ge=0, le=Decimal("100000000"), decimal_places=3)
    usual_price: Decimal | None = Field(default=None, ge=0, le=Decimal("100000000"), decimal_places=3)
    preferred: bool = False
    is_active: bool = True

    @field_validator("name", "place")
    @classmethod
    def one_line(cls, v: str) -> str:
        return " ".join((v or "").split())

    @field_validator("description", "notes")
    @classmethod
    def text(cls, v: str) -> str:
        return clean_text(v or "", multiline=True)

    @field_validator("link")
    @classmethod
    def web_link(cls, v):
        v = (v or "").strip()
        if not v:
            return None
        if not v.startswith(("https://", "http://")) or any(c.isspace() for c in v):
            raise ValueError("The link must start with https://")
        return v

    @field_validator("image_url")
    @classmethod
    def own_photo(cls, v):
        v = (v or "").strip()
        if not v:
            return None
        if not v.startswith("/api/media/"):
            raise ValueError("Upload the photo (photos from other websites can't be used)")
        return v


class SupplierOut(SupplierIn):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: int
    bookings: int = 0


def _get(db: Session, me: User, supplier_id: int) -> Supplier:
    s = db.get(Supplier, supplier_id)
    if s is None or s.company_id != me.company_id:
        raise HTTPException(404, "Supplier not found")
    return s


def _check_photo(db: Session, me: User, body: SupplierIn) -> None:
    if body.image_url and not media_belongs_to(db, body.image_url, me.company_id):
        raise HTTPException(422, "Upload the photo (photos from other websites can't be used)")


def _out(s: Supplier, bookings: dict[int, int]) -> SupplierOut:
    out = SupplierOut.model_validate(s)
    out.bookings = bookings.get(s.id, 0)
    return out


def _bookings(db: Session, company_id: int) -> dict[int, int]:
    return dict(db.execute(select(TripOption.supplier_id, func.count(TripOption.id)).where(
        TripOption.company_id == company_id, TripOption.chosen.is_(True), TripOption.supplier_id.is_not(None))
        .group_by(TripOption.supplier_id)).all())


@router.get("", response_model=list[SupplierOut])
def list_suppliers(category: Part | None = None, q: str | None = Query(default=None, max_length=100),
                   me: User = Depends(viewer), db: Session = Depends(get_db)):
    stmt = select(Supplier).where(Supplier.company_id == me.company_id)
    if category:
        stmt = stmt.where(Supplier.category == category)
    if q and q.strip():
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(Supplier.name).like(like), func.lower(Supplier.place).like(like)))
    rows = db.scalars(stmt.order_by(Supplier.preferred.desc(), Supplier.category, Supplier.name).limit(1000)).all()
    counts = _bookings(db, me.company_id)
    return [_out(s, counts) for s in rows]


@router.post("", response_model=SupplierOut, status_code=201)
def create_supplier(body: SupplierIn, me: User = Depends(editor), db: Session = Depends(get_db)):
    _check_photo(db, me, body)
    if (db.scalar(select(func.count(Supplier.id)).where(Supplier.company_id == me.company_id)) or 0) >= svc.MAX_SUPPLIERS:
        raise HTTPException(409, "The library is full")
    s = Supplier(company_id=me.company_id, **body.model_dump())
    db.add(s)
    audit(db, me, "supplier.created", target=body.name)
    db.commit()
    db.refresh(s)
    return _out(s, {})


@router.put("/{supplier_id}", response_model=SupplierOut)
def update_supplier(supplier_id: int, body: SupplierIn, me: User = Depends(editor), db: Session = Depends(get_db)):
    s = _get(db, me, supplier_id)
    _check_photo(db, me, body)
    for k, v in body.model_dump().items():
        setattr(s, k, v)
    db.commit()
    db.refresh(s)
    return _out(s, _bookings(db, me.company_id))


@router.delete("/{supplier_id}", status_code=204)
def delete_supplier(supplier_id: int, me: User = Depends(editor), db: Session = Depends(get_db)):
    s = _get(db, me, supplier_id)
    audit(db, me, "supplier.deleted", target=s.name)
    db.delete(s)  # the choices that used it keep their own copy of the details
    db.commit()


@router.get("/stats")
def library_stats(days: int = Query(default=365, ge=7, le=1095), me: User = Depends(viewer), db: Session = Depends(get_db)):
    require_addon(me.company, "library_analytics")
    return svc.stats(db, me.company_id, days)


@router.get("/margins")
def library_margins(me: User = Depends(viewer), db: Session = Depends(get_db)):
    require_addon(me.company, "library_margins")
    return svc.margins(db, me.company_id)
