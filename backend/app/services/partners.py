"""Rules of the business accounts (clients and vendors) of a travel company.

Everything here works inside one travel company: every query is filtered by its id, so a company can
never see or change another company's accounts, logins or numbers. Rules that count accounts or
logins lock the company row first, so two requests at the same moment cannot both pass the limit.
"""

from fastapi import HTTPException, status
from sqlalchemy import func, select, true, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import audit
from ..b2b import B2BSettings, b2b_settings, clean_features, effective_features, features_of
from ..models import Company, Customer, Partner, PartnerKind, PartnerPhone, Role, User
from ..partner_schemas import (
    B2BUsage,
    PartnerIn,
    PartnerLoginIn,
    PartnerLoginOut,
    PartnerLoginUpdate,
    PartnerOut,
    PartnerUpdate,
)
from ..security import hash_password, revoke_sessions_now, strong_password
from .whatsapp import normalize_phone


def _lock_company(db: Session, company_id: int) -> None:
    db.execute(select(Company.id).where(Company.id == company_id).with_for_update())


def require_enabled(company: Company) -> B2BSettings:
    settings = b2b_settings(company)
    if not settings.enabled:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Business accounts are not switched on for your company. Ask the platform admin.")
    return settings


def usage(db: Session, company_id: int) -> B2BUsage:
    rows = dict(db.execute(select(Partner.kind, func.count(Partner.id))
                           .where(Partner.company_id == company_id).group_by(Partner.kind)).all())
    return B2BUsage(clients=rows.get(PartnerKind.CLIENT, 0), vendors=rows.get(PartnerKind.VENDOR, 0))


def get_partner(db: Session, company_id: int, partner_id: int) -> Partner:
    partner = db.get(Partner, partner_id)
    if partner is None or partner.company_id != company_id:
        raise HTTPException(404, "Business account not found")
    return partner


def login_out(user: User) -> PartnerLoginOut:
    return PartnerLoginOut(id=user.id, email=user.email, full_name=user.full_name, is_active=user.is_active,
                           created_at=user.created_at, last_login_at=user.last_login_at)


def partner_out(db: Session, partner: Partner) -> PartnerOut:
    logins = db.scalars(select(User).where(User.partner_id == partner.id, User.company_id == partner.company_id)
                        .order_by(User.id)).all()
    return PartnerOut(
        id=partner.id, kind=partner.kind, name=partner.name, contact_name=partner.contact_name,
        contact_email=partner.contact_email, contact_phone=partner.contact_phone, notes=partner.notes,
        features=clean_features(partner.features, partner.kind), active_features=effective_features(partner),
        whatsapp_numbers=[p.phone for p in partner.phones], is_active=partner.is_active,
        created_at=partner.created_at, logins=[login_out(u) for u in logins],
    )


def _check_features(settings: B2BSettings, kind: str, features: list[str]) -> list[str]:
    wrong = sorted(set(features) - set(features_of(kind)))
    if wrong:
        raise HTTPException(422, f"Not a feature of this kind of account: {', '.join(wrong)}")
    not_allowed = sorted(set(features) - set(settings.features))
    if not_allowed:
        raise HTTPException(403, f"The platform admin has not allowed: {', '.join(not_allowed)}")
    return clean_features(features, kind)


def _clean_numbers(numbers: list[str]) -> list[str]:
    out: list[str] = []
    for raw in numbers:
        if not (raw or "").strip():
            continue
        phone = normalize_phone(raw)
        if phone is None:
            raise HTTPException(422, f"Not a valid WhatsApp number: {raw.strip()[:30]}. Write it with the country "
                                     "code, for example +968 9123 4567")
        if phone not in out:
            out.append(phone)
    return out


def _set_numbers(db: Session, partner: Partner, numbers: list[str]) -> None:
    """Links the numbers to this account, and the customers who already wrote from them."""
    numbers = _clean_numbers(numbers)
    if numbers:
        taken = db.execute(select(PartnerPhone.phone, Partner.name).join(Partner, Partner.id == PartnerPhone.partner_id)
                           .where(PartnerPhone.company_id == partner.company_id, PartnerPhone.phone.in_(numbers),
                                  PartnerPhone.partner_id != partner.id)).first()
        if taken:
            raise HTTPException(409, f"+{taken[0]} is already linked to {taken[1]}")
    keep = set(numbers)
    for row in list(partner.phones):
        if row.phone not in keep:
            partner.phones.remove(row)
    have = {p.phone for p in partner.phones}
    for phone in numbers:
        if phone not in have:
            partner.phones.append(PartnerPhone(company_id=partner.company_id, phone=phone))
    db.flush()
    # Customers of this company follow their number.
    db.execute(update(Customer).where(Customer.company_id == partner.company_id, Customer.partner_id == partner.id,
                                      Customer.whatsapp_id.not_in(numbers) if numbers else true())
               .values(partner_id=None).execution_options(synchronize_session=False))
    if numbers:
        db.execute(update(Customer).where(Customer.company_id == partner.company_id, Customer.whatsapp_id.in_(numbers))
                   .values(partner_id=partner.id).execution_options(synchronize_session=False))


def create_partner(db: Session, company: Company, data: PartnerIn, acting_user: User) -> Partner:
    settings = require_enabled(company)
    features = _check_features(settings, data.kind, data.features)
    _lock_company(db, company.id)
    used = usage(db, company.id)
    count = used.clients if data.kind == PartnerKind.CLIENT else used.vendors
    limit = settings.limit(data.kind)
    if count >= limit:
        what = "client" if data.kind == PartnerKind.CLIENT else "vendor"
        raise HTTPException(409, f"Limit reached: {count}/{limit} {what} accounts. Ask the platform admin to raise it.")
    partner = Partner(company_id=company.id, kind=data.kind, name=data.name, contact_name=data.contact_name,
                      contact_email=data.contact_email, contact_phone=data.contact_phone, notes=data.notes,
                      features=features, is_active=data.is_active)
    db.add(partner)
    db.flush()
    try:
        _set_numbers(db, partner, data.whatsapp_numbers if data.kind == PartnerKind.CLIENT else [])
    except IntegrityError as exc:  # the same number saved at the same moment
        db.rollback()
        raise HTTPException(409, "One of these WhatsApp numbers is already linked to another account") from exc
    audit(db, acting_user, "partner.created", target=partner.name, detail=partner.kind, company_id=company.id)
    db.commit()
    db.refresh(partner)
    return partner


def update_partner(db: Session, partner: Partner, data: PartnerUpdate, acting_user: User) -> Partner:
    settings = require_enabled(partner.company)
    fields = data.model_dump(exclude_unset=True)
    if "features" in fields and fields["features"] is not None:
        # Features the owner took back stay saved (they work again if allowed again); new ones must be allowed.
        new = set(fields["features"]) - set(partner.features or [])
        _check_features(settings, partner.kind, sorted(new))
        wrong = sorted(set(fields["features"]) - set(features_of(partner.kind)))
        if wrong:
            raise HTTPException(422, f"Not a feature of this kind of account: {', '.join(wrong)}")
        partner.features = clean_features(fields["features"], partner.kind)
    for key in ("name", "contact_name", "contact_email", "contact_phone", "notes"):
        if key in fields and not (key == "name" and fields[key] is None):
            setattr(partner, key, fields[key])
    if fields.get("is_active") is not None and fields["is_active"] != partner.is_active:
        partner.is_active = fields["is_active"]
        if not partner.is_active:
            # Pausing an account ends its open sessions at once.
            db.execute(update(User).where(User.partner_id == partner.id, User.company_id == partner.company_id)
                       .values(tokens_valid_after=revoke_sessions_now()).execution_options(synchronize_session=False))
    if fields.get("whatsapp_numbers") is not None:
        if partner.kind != PartnerKind.CLIENT and fields["whatsapp_numbers"]:
            raise HTTPException(422, "Only business clients can have linked WhatsApp numbers")
        try:
            _set_numbers(db, partner, fields["whatsapp_numbers"])
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(409, "One of these WhatsApp numbers is already linked to another account") from exc
    audit(db, acting_user, "partner.updated", target=partner.name, company_id=partner.company_id)
    db.commit()
    db.refresh(partner)
    return partner


def delete_partner(db: Session, partner: Partner, acting_user: User) -> None:
    name, company_id = partner.name, partner.company_id
    db.execute(update(Customer).where(Customer.company_id == company_id, Customer.partner_id == partner.id)
               .values(partner_id=None).execution_options(synchronize_session=False))
    for user in db.scalars(select(User).where(User.partner_id == partner.id, User.company_id == company_id)).all():
        db.delete(user)
    db.delete(partner)
    audit(db, acting_user, "partner.deleted", target=name, company_id=company_id)
    db.commit()


# --- Logins of a business account -----------------------------------------------------------------

def get_login(db: Session, partner: Partner, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None or user.partner_id != partner.id or user.company_id != partner.company_id:
        raise HTTPException(404, "Login not found")
    return user


def _check_email_free(db: Session, company_id: int, email: str, exclude_user_id: int | None = None) -> None:
    existing = db.scalar(select(User).where(User.company_id == company_id, User.email == email))
    if existing is not None and existing.id != exclude_user_id:
        raise HTTPException(409, "An account with this email already exists in this company")


def create_login(db: Session, partner: Partner, data: PartnerLoginIn, acting_user: User) -> tuple[User, str]:
    settings = require_enabled(partner.company)
    password = strong_password()
    password_hash = hash_password(password)  # slow: before the lock
    _lock_company(db, partner.company_id)
    used = db.scalar(select(func.count(User.id)).where(User.partner_id == partner.id, User.is_active.is_(True))) or 0
    if used >= settings.max_users_per_partner:
        raise HTTPException(409, f"Login limit reached ({used}/{settings.max_users_per_partner}) for this account. "
                                 "Ask the platform admin to raise it.")
    email = data.email.lower()
    _check_email_free(db, partner.company_id, email)
    user = User(company_id=partner.company_id, partner_id=partner.id, email=email, full_name=data.full_name,
                password_hash=password_hash, role=Role.PARTNER, permissions=[], is_active=True)
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "An account with this email already exists in this company") from exc
    audit(db, acting_user, "partner.login_created", target=f"{partner.name}: {user.full_name}",
          company_id=partner.company_id)
    db.commit()
    db.refresh(user)
    return user, password


def update_login(db: Session, partner: Partner, user: User, data: PartnerLoginUpdate,
                 acting_user: User) -> tuple[User, str | None]:
    settings = require_enabled(partner.company)
    password = strong_password() if data.new_password else None
    password_hash = hash_password(password) if password else None
    _lock_company(db, partner.company_id)
    db.refresh(user)
    if data.is_active and not user.is_active:
        used = db.scalar(select(func.count(User.id)).where(User.partner_id == partner.id, User.is_active.is_(True))) or 0
        if used >= settings.max_users_per_partner:
            raise HTTPException(409, f"Login limit reached ({used}/{settings.max_users_per_partner}) for this account.")
    if data.email is not None:
        email = data.email.lower()
        _check_email_free(db, partner.company_id, email, exclude_user_id=user.id)
        user.email = email
    if data.full_name is not None:
        user.full_name = " ".join(data.full_name.split())
    if data.is_active is not None:
        user.is_active = data.is_active
        if not data.is_active:
            user.tokens_valid_after = revoke_sessions_now()
    if password_hash:
        user.password_hash = password_hash
        user.tokens_valid_after = revoke_sessions_now()
    audit(db, acting_user, "partner.login_updated", target=f"{partner.name}: {user.full_name}",
          detail="new password" if password else None, company_id=partner.company_id)
    db.commit()
    db.refresh(user)
    return user, password


def delete_login(db: Session, partner: Partner, user: User, acting_user: User) -> None:
    audit(db, acting_user, "partner.login_deleted", target=f"{partner.name}: {user.full_name}",
          company_id=partner.company_id)
    db.delete(user)
    db.commit()


# --- WhatsApp -----------------------------------------------------------------------------------------

def partner_for_whatsapp(db: Session, company_id: int, wa_id: str) -> int | None:
    """The business client whose linked number this is (inside this travel company only)."""
    return db.scalar(select(PartnerPhone.partner_id).where(PartnerPhone.company_id == company_id,
                                                           PartnerPhone.phone == wa_id))


# --- Platform owner -----------------------------------------------------------------------------------

def save_settings(db: Session, company: Company, settings: B2BSettings, acting_user: User) -> B2BSettings:
    company.b2b = settings.model_dump()
    audit(db, acting_user, "b2b.settings_saved", target=company.name,
          detail="on" if settings.enabled else "off", company_id=company.id)
    db.commit()
    return settings
