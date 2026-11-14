"""Business accounts (clients and vendors).

* ``/api/system/companies/{id}/b2b``: the platform owner switches them on and sets limits and features.
* ``/api/partners``: a travel company manages its own clients, vendors and their logins
  (``partners.manage`` permission).
* ``/api/partner``: the portal of a client or vendor login.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..b2b import FEATURES, B2BSettings, b2b_settings, effective_features
from ..branding import get_branding
from ..database import get_db
from ..deps import get_partner_user, require_permission, require_system_admin
from ..models import Company, Partner, User
from ..partner_schemas import (
    B2BOverview,
    PartnerHome,
    PartnerIn,
    PartnerListOut,
    PartnerLoginCreated,
    PartnerLoginIn,
    PartnerLoginUpdate,
    PartnerOut,
    PartnerUpdate,
)
from ..services import partners as svc

router = APIRouter(tags=["business accounts"])

manage = require_permission("partners.manage")


def _overview(db: Session, company: Company) -> B2BOverview:
    return B2BOverview(settings=b2b_settings(company), usage=svc.usage(db, company.id), catalog=FEATURES)


# --- Platform owner -----------------------------------------------------------------------------------

def _company(db: Session, company_id: int) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "Company not found")
    return company


@router.get("/api/system/companies/{company_id}/b2b", response_model=B2BOverview)
def owner_get(company_id: int, _: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    return _overview(db, _company(db, company_id))


@router.put("/api/system/companies/{company_id}/b2b", response_model=B2BOverview)
def owner_save(company_id: int, body: B2BSettings, me: User = Depends(require_system_admin),
               db: Session = Depends(get_db)):
    company = _company(db, company_id)
    svc.save_settings(db, company, body, me)
    return _overview(db, company)


# --- Travel company -----------------------------------------------------------------------------------

@router.get("/api/partners/settings", response_model=B2BOverview)
def company_settings(me: User = Depends(manage), db: Session = Depends(get_db)):
    """The owner's limits and allowed features (readable even when switched off, to explain why)."""
    return _overview(db, me.company)


@router.get("/api/partners", response_model=PartnerListOut)
def list_partners(me: User = Depends(manage), db: Session = Depends(get_db)):
    svc.require_enabled(me.company)
    partners = db.scalars(select(Partner).where(Partner.company_id == me.company_id)
                          .order_by(Partner.kind, Partner.name)).all()
    return PartnerListOut(**_overview(db, me.company).model_dump(),
                          partners=[svc.partner_out(db, p) for p in partners])


@router.post("/api/partners", response_model=PartnerOut, status_code=201)
def create_partner(body: PartnerIn, me: User = Depends(manage), db: Session = Depends(get_db)):
    return svc.partner_out(db, svc.create_partner(db, me.company, body, me))


@router.patch("/api/partners/{partner_id}", response_model=PartnerOut)
def update_partner(partner_id: int, body: PartnerUpdate, me: User = Depends(manage), db: Session = Depends(get_db)):
    partner = svc.get_partner(db, me.company_id, partner_id)
    return svc.partner_out(db, svc.update_partner(db, partner, body, me))


@router.delete("/api/partners/{partner_id}", status_code=204)
def delete_partner(partner_id: int, me: User = Depends(manage), db: Session = Depends(get_db)):
    svc.require_enabled(me.company)
    svc.delete_partner(db, svc.get_partner(db, me.company_id, partner_id), me)


@router.post("/api/partners/{partner_id}/logins", response_model=PartnerLoginCreated, status_code=201)
def create_login(partner_id: int, body: PartnerLoginIn, me: User = Depends(manage), db: Session = Depends(get_db)):
    partner = svc.get_partner(db, me.company_id, partner_id)
    user, password = svc.create_login(db, partner, body, me)
    return PartnerLoginCreated(login=svc.login_out(user), password=password)


@router.patch("/api/partners/{partner_id}/logins/{user_id}", response_model=PartnerLoginCreated)
def update_login(partner_id: int, user_id: int, body: PartnerLoginUpdate, me: User = Depends(manage),
                 db: Session = Depends(get_db)):
    partner = svc.get_partner(db, me.company_id, partner_id)
    user, password = svc.update_login(db, partner, svc.get_login(db, partner, user_id), body, me)
    return PartnerLoginCreated(login=svc.login_out(user), password=password)


@router.delete("/api/partners/{partner_id}/logins/{user_id}", status_code=204)
def delete_login(partner_id: int, user_id: int, me: User = Depends(manage), db: Session = Depends(get_db)):
    svc.require_enabled(me.company)
    partner = svc.get_partner(db, me.company_id, partner_id)
    svc.delete_login(db, partner, svc.get_login(db, partner, user_id), me)


# --- Business portal ----------------------------------------------------------------------------------

@router.get("/api/partner/home", response_model=PartnerHome)
def partner_home(me: User = Depends(get_partner_user)):
    partner, company = me.partner, me.company
    return PartnerHome(
        partner_id=partner.id, partner_name=partner.name, kind=partner.kind, company_name=company.name,
        company_slug=company.slug, logo=get_branding(company).logo, features=effective_features(partner, company),
        catalog=FEATURES, whatsapp_numbers=[p.phone for p in partner.phones],
        company_whatsapp=company.whatsapp_display_number,
    )
