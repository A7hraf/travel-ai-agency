"""Advanced features switched by the platform owner, and the members community of a travel company.

* ``/api/system/companies/{id}/addons``: the platform owner switches advanced features on or off.
* ``/api/members``: staff with ``members.manage`` set up the levels, give ranks and handle requests.
Every query is limited to the employee's company.
"""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..addons import ADDONS, AddonSettings, addon_settings, has_addon
from ..audit import audit
from ..database import get_db
from ..deps import require_permission, require_system_admin
from ..members import LEVELS, LevelKey, MembershipConfig, membership_config
from ..models import Company, Customer, MemberRequest, User, utcnow

router = APIRouter(tags=["members"])

STATUSES = ("open", "in_progress", "done", "declined")


# --- Platform owner: advanced features ----------------------------------------------------------------

class AddonsOut(BaseModel):
    addons: AddonSettings
    catalog: dict[str, str]


def _company(db: Session, company_id: int) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "Company not found")
    return company


@router.get("/api/system/companies/{company_id}/addons", response_model=AddonsOut)
def get_addons(company_id: int, _: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    return AddonsOut(addons=addon_settings(_company(db, company_id)), catalog=ADDONS)


@router.put("/api/system/companies/{company_id}/addons", response_model=AddonsOut)
def save_addons(company_id: int, body: AddonSettings, me: User = Depends(require_system_admin),
                db: Session = Depends(get_db)):
    company = _company(db, company_id)
    company.addons = body.model_dump()
    audit(db, me, "addons.saved", target=company.name,
          detail=", ".join(k for k, v in body.model_dump().items() if v) or "none", company_id=company.id)
    db.commit()
    return AddonsOut(addons=body, catalog=ADDONS)


# --- Travel company: members --------------------------------------------------------------------------

def manager(user: User = Depends(require_permission("members.manage"))) -> User:
    if not has_addon(user.company, "members"):
        raise HTTPException(403, "The members community is not switched on for your company. Ask the platform admin.")
    return user


class MemberRow(BaseModel):
    customer_id: int
    name: str | None
    phone: str | None
    email: str | None
    level: str
    member_since: datetime | None
    note: str | None


class MemberList(BaseModel):
    members: list[MemberRow]
    counts: dict[str, int]
    config: MembershipConfig


class MemberUpdate(BaseModel):
    level: LevelKey | None  # None removes the membership
    note: str | None = Field(default=None, max_length=500)

    @field_validator("note")
    @classmethod
    def one_line(cls, v):
        return " ".join(v.split()) or None if v is not None else None


class RequestOut(BaseModel):
    id: int
    customer_id: int
    customer_name: str | None
    customer_phone: str | None
    conversation_id: int | None
    kind: str
    level: str | None
    title: str
    details: str | None
    status: str
    staff_note: str | None
    handled_by: str | None
    created_at: datetime
    updated_at: datetime


class RequestIn(BaseModel):
    customer_id: int
    kind: Literal["special", "join"] = "special"
    title: str = Field(min_length=2, max_length=200)
    details: str | None = Field(default=None, max_length=4000)


class RequestUpdate(BaseModel):
    status: Literal["open", "in_progress", "done", "declined"] | None = None
    staff_note: str | None = Field(default=None, max_length=4000)


def _row(c: Customer) -> MemberRow:
    return MemberRow(customer_id=c.id, name=c.name, phone=c.phone, email=c.email, level=c.member_level,
                     member_since=c.member_since, note=c.member_note)


def request_out(r: MemberRequest) -> RequestOut:
    return RequestOut(id=r.id, customer_id=r.customer_id, customer_name=r.customer.name, customer_phone=r.customer.phone,
                      conversation_id=r.conversation_id, kind=r.kind, level=r.level, title=r.title, details=r.details,
                      status=r.status, staff_note=r.staff_note,
                      handled_by=r.handled_by.full_name if r.handled_by else None,
                      created_at=r.created_at, updated_at=r.updated_at)


def _customer(db: Session, me: User, customer_id: int) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None or customer.company_id != me.company_id:
        raise HTTPException(404, "Customer not found")
    return customer


@router.get("/api/members/settings", response_model=MembershipConfig)
def get_settings(me: User = Depends(manager)):
    return membership_config(me.company)


@router.put("/api/members/settings", response_model=MembershipConfig)
def save_settings(body: MembershipConfig, me: User = Depends(manager), db: Session = Depends(get_db)):
    me.company.membership = body.model_dump()
    audit(db, me, "members.settings_saved")
    db.commit()
    return body


@router.get("/api/members", response_model=MemberList)
def list_members(level: LevelKey | None = None, me: User = Depends(manager), db: Session = Depends(get_db)):
    stmt = select(Customer).where(Customer.company_id == me.company_id, Customer.member_level.is_not(None))
    if level:
        stmt = stmt.where(Customer.member_level == level)
    members = db.scalars(stmt.order_by(Customer.member_since.desc()).limit(2000)).all()
    counts = dict(db.execute(select(Customer.member_level, func.count(Customer.id))
                             .where(Customer.company_id == me.company_id, Customer.member_level.is_not(None))
                             .group_by(Customer.member_level)).all())
    return MemberList(members=[_row(c) for c in members], counts={k: counts.get(k, 0) for k in LEVELS},
                      config=membership_config(me.company))


@router.put("/api/members/{customer_id}", response_model=MemberRow | None)
def set_member(customer_id: int, body: MemberUpdate, me: User = Depends(manager), db: Session = Depends(get_db)):
    customer = _customer(db, me, customer_id)
    before = customer.member_level
    if body.level is None:
        customer.member_level = customer.member_since = customer.member_note = None
    else:
        if customer.member_level is None:
            customer.member_since = utcnow()
        customer.member_level = body.level
        customer.member_note = body.note
    if before != customer.member_level:
        audit(db, me, "member.level", target=customer.name or f"#{customer.id}",
              detail=f"{before or '-'} → {customer.member_level or '-'}")
    db.commit()
    return _row(customer) if customer.member_level else None


@router.get("/api/members/requests", response_model=list[RequestOut])
def list_requests(status: str | None = Query(default=None, max_length=15), me: User = Depends(manager),
                  db: Session = Depends(get_db)):
    stmt = select(MemberRequest).where(MemberRequest.company_id == me.company_id)
    if status:
        stmt = stmt.where(MemberRequest.status == status)
    reqs = db.scalars(stmt.order_by(MemberRequest.created_at.desc()).limit(500)).all()
    return [request_out(r) for r in reqs]


@router.post("/api/members/requests", response_model=RequestOut, status_code=201)
def create_request(body: RequestIn, me: User = Depends(manager), db: Session = Depends(get_db)):
    customer = _customer(db, me, body.customer_id)
    req = MemberRequest(company_id=me.company_id, customer_id=customer.id, kind=body.kind,
                        level=customer.member_level, title=" ".join(body.title.split()),
                        details=(body.details or "").strip() or None)
    db.add(req)
    audit(db, me, "member.request_created", target=customer.name or f"#{customer.id}", detail=req.title)
    db.commit()
    db.refresh(req)
    return request_out(req)


@router.patch("/api/members/requests/{request_id}", response_model=RequestOut)
def update_request(request_id: int, body: RequestUpdate, me: User = Depends(manager), db: Session = Depends(get_db)):
    req = db.get(MemberRequest, request_id)
    if req is None or req.company_id != me.company_id:
        raise HTTPException(404, "Request not found")
    data = body.model_dump(exclude_unset=True)
    if data.get("status") and data["status"] != req.status:
        req.status = data["status"]
        req.handled_by_id = me.id
        audit(db, me, "member.request_status", target=req.title, detail=req.status)
    if "staff_note" in data:
        req.staff_note = (data["staff_note"] or "").strip() or None
    db.commit()
    db.refresh(req)
    return request_out(req)
