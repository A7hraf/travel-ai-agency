"""Business trip requests: the travel company (``/api/b2b/requests``), the client portal
(``/api/partner/requests``) and the vendor portal (``/api/partner/jobs``). Each answers with its own view."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..addons import has_addon, use
from ..b2b import effective_features
from ..database import get_db
from ..deps import get_partner_user, require_permission
from ..models import Partner, PartnerKind, TripRequest, User
from ..services import partners as partners_svc
from ..services import b2b_flow as flow
from ..services import trip_requests as svc
from ..services.trip_requests import Actor
from ..ai import planner
from ..ratelimit import limiter
from ..trip_schemas import (
    AssignVendorIn,
    BookedIn,
    ChangesIn,
    ChooseIn,
    ClientTripOut,
    MarkupIn,
    MessageIn,
    OptionIn,
    PaidIn,
    PaymentPlanIn,
    RateIn,
    ReasonIn,
    SendToClientIn,
    StaffRequestIn,
    StaffTripOut,
    StaffTripRow,
    TripRequestIn,
    VendorOptionIn,
    VendorTripOut,
)

router = APIRouter(tags=["business requests"])


# --- Travel company -----------------------------------------------------------------------------------

def staff(user: User = Depends(require_permission("requests.manage"))) -> User:
    """Trip requests come from business clients (business accounts on) or individual travellers (AI trip
    planner on); either switch, set by the platform owner, opens this page."""
    if not has_addon(user.company, "trip_planner"):
        partners_svc.require_enabled(user.company)
    return user


def _staff_out(db: Session, me: User, req: TripRequest) -> StaffTripOut:
    return svc.staff_view(req, me.company)


@router.get("/api/b2b/requests", response_model=list[StaffTripRow])
def staff_list(status: str | None = Query(default=None, max_length=20), client_id: int | None = None,
               me: User = Depends(staff), db: Session = Depends(get_db)):
    stmt = select(TripRequest).where(TripRequest.company_id == me.company_id)
    if status:
        stmt = stmt.where(TripRequest.status == status)
    if client_id:
        stmt = stmt.where(TripRequest.client_id == client_id)
    return [svc.staff_row(r) for r in db.scalars(stmt.order_by(TripRequest.updated_at.desc()).limit(500)).all()]


@router.post("/api/b2b/requests", response_model=StaffTripOut, status_code=201)
def staff_create(body: StaffRequestIn, me: User = Depends(staff), db: Session = Depends(get_db)):
    client = db.get(Partner, body.client_id)
    if client is None or client.company_id != me.company_id:
        raise HTTPException(404, "Business client not found")
    req = svc.create_request(db, me.company, client, body, Actor.of(me, "staff"), "staff")
    return _staff_out(db, me, req)


@router.get("/api/b2b/requests/{request_id}", response_model=StaffTripOut)
def staff_get(request_id: int, me: User = Depends(staff), db: Session = Depends(get_db)):
    return _staff_out(db, me, svc.get_for_company(db, me.company_id, request_id))


@router.post("/api/b2b/requests/{request_id}/vendor", response_model=StaffTripOut)
def staff_assign(request_id: int, body: AssignVendorIn, me: User = Depends(staff), db: Session = Depends(get_db)):
    req = svc.get_for_company(db, me.company_id, request_id, lock=True)
    return _staff_out(db, me, svc.assign_vendor(db, req, body, Actor.of(me, "staff")))


@router.put("/api/b2b/requests/{request_id}/markup", response_model=StaffTripOut)
def staff_markup(request_id: int, body: MarkupIn, me: User = Depends(staff), db: Session = Depends(get_db)):
    req = svc.get_for_company(db, me.company_id, request_id, lock=True)
    return _staff_out(db, me, svc.set_markup(db, req, body.markup_percent, Actor.of(me, "staff")))


@router.post("/api/b2b/requests/{request_id}/options", response_model=StaffTripOut)
def staff_add_option(request_id: int, body: OptionIn, me: User = Depends(staff), db: Session = Depends(get_db)):
    req = svc.get_for_company(db, me.company_id, request_id, lock=True)
    return _staff_out(db, me, svc.add_staff_option(db, req, body, Actor.of(me, "staff")))


@router.put("/api/b2b/requests/{request_id}/options/{option_id}", response_model=StaffTripOut)
def staff_update_option(request_id: int, option_id: int, body: OptionIn, me: User = Depends(staff),
                        db: Session = Depends(get_db)):
    req = svc.get_for_company(db, me.company_id, request_id, lock=True)
    return _staff_out(db, me, svc.update_staff_option(db, req, option_id, body, Actor.of(me, "staff")))


@router.delete("/api/b2b/requests/{request_id}/options/{option_id}", response_model=StaffTripOut)
def staff_delete_option(request_id: int, option_id: int, me: User = Depends(staff), db: Session = Depends(get_db)):
    req = svc.get_for_company(db, me.company_id, request_id, lock=True)
    return _staff_out(db, me, svc.delete_option(db, req, option_id, Actor.of(me, "staff")))


@router.post("/api/b2b/requests/{request_id}/ai-draft", response_model=StaffTripOut)
def staff_ai_draft(request_id: int, me: User = Depends(staff), db: Session = Depends(get_db)):
    """The AI planner drafts up to 3 options per part (with estimates for staff only)."""
    use(db, me, "trip_planner")
    limiter.check(f"ai-draft:{me.company_id}", 30, "The AI planner is busy: please try again in a few minutes", window=3600)
    req = svc.get_for_company(db, me.company_id, request_id, lock=True)
    return _staff_out(db, me, planner.draft_options(db, req, me.company, Actor.of(me, "staff")))


@router.post("/api/b2b/requests/{request_id}/send", response_model=StaffTripOut)
def staff_send(request_id: int, body: SendToClientIn, me: User = Depends(staff), db: Session = Depends(get_db)):
    req = svc.get_for_company(db, me.company_id, request_id, lock=True)
    return _staff_out(db, me, svc.send_to_client(db, req, body.option_ids, Actor.of(me, "staff")))


@router.post("/api/b2b/requests/{request_id}/approve", response_model=StaffTripOut)
def staff_approve(request_id: int, me: User = Depends(staff), db: Session = Depends(get_db)):
    req = svc.get_for_company(db, me.company_id, request_id, lock=True)
    return _staff_out(db, me, svc.approve(db, req, Actor.of(me, "staff")))


@router.post("/api/b2b/requests/{request_id}/booked", response_model=StaffTripOut)
def staff_booked(request_id: int, body: BookedIn, me: User = Depends(staff), db: Session = Depends(get_db)):
    """For trips the travel company books itself (no vendor, or on the vendor's behalf)."""
    req = svc.get_for_company(db, me.company_id, request_id, lock=True)
    return _staff_out(db, me, svc.mark_booked(db, req, body, Actor.of(me, "staff")))


@router.post("/api/b2b/requests/{request_id}/complete", response_model=StaffTripOut)
def staff_complete(request_id: int, me: User = Depends(staff), db: Session = Depends(get_db)):
    req = svc.get_for_company(db, me.company_id, request_id, lock=True)
    return _staff_out(db, me, svc.complete(db, req, Actor.of(me, "staff")))


@router.post("/api/b2b/requests/{request_id}/cancel", response_model=StaffTripOut)
def staff_cancel(request_id: int, body: ReasonIn, me: User = Depends(staff), db: Session = Depends(get_db)):
    req = svc.get_for_company(db, me.company_id, request_id, lock=True)
    return _staff_out(db, me, svc.cancel(db, req, Actor.of(me, "staff"), body.reason))


@router.post("/api/b2b/requests/{request_id}/messages", response_model=StaffTripOut)
def staff_message(request_id: int, body: MessageIn, me: User = Depends(staff), db: Session = Depends(get_db)):
    if body.thread is None:
        raise HTTPException(422, "Choose the client or the vendor thread")
    req = svc.get_for_company(db, me.company_id, request_id)
    if body.thread == "vendor" and req.vendor_id is None:
        raise HTTPException(409, "This request has no vendor yet")
    return _staff_out(db, me, svc.post_message(db, req, body.thread, Actor.of(me, "staff"), body.text))


# --- Client portal ------------------------------------------------------------------------------------

def _client(user: User, *need: str) -> User:
    partner = user.partner
    if partner.kind != PartnerKind.CLIENT:
        raise HTTPException(403, "This area is for business clients")
    have = set(effective_features(partner))
    if not any(f in have for f in need):
        raise HTTPException(403, "This service is not switched on for your account")
    return user


def client_reader(user: User = Depends(get_partner_user)) -> User:
    return _client(user, "client.requests", "client.history")


def client_writer(user: User = Depends(get_partner_user)) -> User:
    return _client(user, "client.requests")


@router.get("/api/partner/requests", response_model=list[ClientTripOut])
def client_list(me: User = Depends(client_reader), db: Session = Depends(get_db)):
    reqs = db.scalars(select(TripRequest).where(TripRequest.company_id == me.company_id,
                                                TripRequest.client_id == me.partner_id)
                      .order_by(TripRequest.created_at.desc()).limit(200)).all()
    return [svc.client_view(r, me.company) for r in reqs]


@router.post("/api/partner/requests", response_model=ClientTripOut, status_code=201)
def client_create(body: TripRequestIn, me: User = Depends(client_writer), db: Session = Depends(get_db)):
    req = svc.create_request(db, me.company, me.partner, body, Actor.of(me, "client"), "portal")
    return svc.client_view(req, me.company)


@router.get("/api/partner/requests/{request_id}", response_model=ClientTripOut)
def client_get(request_id: int, me: User = Depends(client_reader), db: Session = Depends(get_db)):
    return svc.client_view(svc.get_for_client(db, me, request_id), me.company)


@router.post("/api/partner/requests/{request_id}/choose", response_model=ClientTripOut)
def client_choose(request_id: int, body: ChooseIn, me: User = Depends(client_writer), db: Session = Depends(get_db)):
    req = svc.get_for_client(db, me, request_id, lock=True)
    return svc.client_view(svc.choose(db, req, body.option_ids, Actor.of(me, "client")), me.company)


@router.post("/api/partner/requests/{request_id}/cancel", response_model=ClientTripOut)
def client_cancel(request_id: int, body: ReasonIn, me: User = Depends(client_writer), db: Session = Depends(get_db)):
    req = svc.get_for_client(db, me, request_id, lock=True)
    return svc.client_view(svc.cancel(db, req, Actor.of(me, "client"), body.reason), me.company)


@router.post("/api/partner/requests/{request_id}/messages", response_model=ClientTripOut)
def client_message(request_id: int, body: MessageIn, me: User = Depends(client_writer), db: Session = Depends(get_db)):
    req = svc.get_for_client(db, me, request_id)
    return svc.client_view(svc.post_message(db, req, "client", Actor.of(me, "client"), body.text), me.company)


# --- Vendor portal ------------------------------------------------------------------------------------

def _vendor(user: User, need: str) -> User:
    partner = user.partner
    if partner.kind != PartnerKind.VENDOR:
        raise HTTPException(403, "This area is for vendors")
    if need not in effective_features(partner):
        raise HTTPException(403, "This service is not switched on for your account")
    return user


def vendor_reader(user: User = Depends(get_partner_user)) -> User:
    return _vendor(user, "vendor.requests")


def vendor_quoter(user: User = Depends(vendor_reader)) -> User:
    return _vendor(user, "vendor.quotes")


@router.get("/api/partner/jobs", response_model=list[VendorTripOut])
def vendor_list(me: User = Depends(vendor_reader), db: Session = Depends(get_db)):
    reqs = db.scalars(select(TripRequest).where(TripRequest.company_id == me.company_id,
                                                TripRequest.vendor_id == me.partner_id)
                      .order_by(TripRequest.updated_at.desc()).limit(200)).all()
    return [svc.vendor_view(r, me.company) for r in reqs]


@router.get("/api/partner/jobs/{request_id}", response_model=VendorTripOut)
def vendor_get(request_id: int, me: User = Depends(vendor_reader), db: Session = Depends(get_db)):
    return svc.vendor_view(svc.get_for_vendor(db, me, request_id), me.company)


@router.post("/api/partner/jobs/{request_id}/accept", response_model=VendorTripOut)
def vendor_accept(request_id: int, me: User = Depends(vendor_reader), db: Session = Depends(get_db)):
    req = svc.get_for_vendor(db, me, request_id, lock=True)
    return svc.vendor_view(svc.vendor_respond(db, req, True, Actor.of(me, "vendor"), None), me.company)


@router.post("/api/partner/jobs/{request_id}/decline", status_code=204)
def vendor_decline(request_id: int, body: ReasonIn, me: User = Depends(vendor_reader), db: Session = Depends(get_db)):
    req = svc.get_for_vendor(db, me, request_id, lock=True)
    svc.vendor_respond(db, req, False, Actor.of(me, "vendor"), body.reason)


@router.post("/api/partner/jobs/{request_id}/options", response_model=VendorTripOut)
def vendor_option(request_id: int, body: VendorOptionIn, me: User = Depends(vendor_quoter),
                  db: Session = Depends(get_db)):
    req = svc.get_for_vendor(db, me, request_id, lock=True)
    return svc.vendor_view(svc.vendor_add_option(db, req, body, Actor.of(me, "vendor")), me.company)


@router.delete("/api/partner/jobs/{request_id}/options/{option_id}", response_model=VendorTripOut)
def vendor_remove_option(request_id: int, option_id: int, me: User = Depends(vendor_quoter),
                         db: Session = Depends(get_db)):
    req = svc.get_for_vendor(db, me, request_id, lock=True)
    return svc.vendor_view(svc.vendor_delete_option(db, req, option_id, Actor.of(me, "vendor")), me.company)


@router.post("/api/partner/jobs/{request_id}/submit", response_model=VendorTripOut)
def vendor_submit(request_id: int, me: User = Depends(vendor_quoter), db: Session = Depends(get_db)):
    req = svc.get_for_vendor(db, me, request_id, lock=True)
    return svc.vendor_view(svc.vendor_submit(db, req, Actor.of(me, "vendor")), me.company)


@router.post("/api/partner/jobs/{request_id}/booked", response_model=VendorTripOut)
def vendor_booked(request_id: int, body: BookedIn, me: User = Depends(vendor_reader), db: Session = Depends(get_db)):
    req = svc.get_for_vendor(db, me, request_id, lock=True)
    return svc.vendor_view(svc.mark_booked(db, req, body, Actor.of(me, "vendor")), me.company)


@router.post("/api/partner/jobs/{request_id}/messages", response_model=VendorTripOut)
def vendor_message(request_id: int, body: MessageIn, me: User = Depends(vendor_reader), db: Session = Depends(get_db)):
    req = svc.get_for_vendor(db, me, request_id)
    return svc.vendor_view(svc.post_message(db, req, "vendor", Actor.of(me, "vendor"), body.text), me.company)


# --- After the first quotation: changes, the payment plan, the rating, the figures ------------------------------

@router.get("/api/b2b/stats")
def staff_stats(days: int = Query(default=90, ge=7, le=730), me: User = Depends(staff), db: Session = Depends(get_db)):
    """B2B earnings, the clients that ask most and the vendors ranked (fastest, best rated, most booked)."""
    return flow.staff_stats(db, me.company, days)


@router.put("/api/b2b/requests/{request_id}/payment-plan", response_model=StaffTripOut)
def staff_plan(request_id: int, body: PaymentPlanIn, me: User = Depends(staff), db: Session = Depends(get_db)):
    req = svc.get_for_company(db, me.company_id, request_id, lock=True)
    return _staff_out(db, me, flow.set_plan(db, req, body.steps, Actor.of(me, "staff")))


@router.post("/api/b2b/requests/{request_id}/payments/{step_id}", response_model=StaffTripOut)
def staff_paid(request_id: int, step_id: int, body: PaidIn, me: User = Depends(staff), db: Session = Depends(get_db)):
    """The client paid this share, or the travel company paid the vendor (or undo)."""
    req = svc.get_for_company(db, me.company_id, request_id, lock=True)
    return _staff_out(db, me, flow.mark_paid(db, req, step_id, body.side, body.reference, body.paid, Actor.of(me, "staff")))


@router.post("/api/partner/requests/{request_id}/changes", response_model=ClientTripOut)
def client_changes(request_id: int, body: ChangesIn, me: User = Depends(client_writer), db: Session = Depends(get_db)):
    """The client wants something else: the vendor gets a clear brief and new options come back."""
    limiter.check(f"b2b-changes:{me.partner_id}", 20, "Too many changes: please wait a little", window=3600)
    req = svc.get_for_client(db, me, request_id, lock=True)
    return svc.client_view(flow.client_changes(db, me.company, req, body.note, Actor.of(me, "client")), me.company)


@router.post("/api/partner/requests/{request_id}/rating", response_model=ClientTripOut)
def client_rate(request_id: int, body: RateIn, me: User = Depends(client_writer), db: Session = Depends(get_db)):
    req = svc.get_for_client(db, me, request_id, lock=True)
    return svc.client_view(flow.rate(db, req, body.rating, body.comment, Actor.of(me, "client")), me.company)


@router.put("/api/partner/jobs/{request_id}/payment-plan", response_model=VendorTripOut)
def vendor_plan(request_id: int, body: PaymentPlanIn, me: User = Depends(vendor_reader), db: Session = Depends(get_db)):
    """The vendor sets when it must be paid: shares of the total with dates (both dashboards follow them)."""
    _vendor(me, "vendor.payments")
    req = svc.get_for_vendor(db, me, request_id, lock=True)
    if not req.vendor_accepted:
        raise HTTPException(409, "Accept the request first")
    return svc.vendor_view(flow.set_plan(db, req, body.steps, Actor.of(me, "vendor")), me.company)


@router.get("/api/partner/quote-settings", response_model=flow.VendorQuoteIn)
def vendor_quote_get(me: User = Depends(vendor_reader)):
    _vendor(me, "vendor.quote_design")
    return flow.VendorQuoteIn.model_validate(me.partner.quote_settings or {})


@router.put("/api/partner/quote-settings", response_model=flow.VendorQuoteIn)
def vendor_quote_put(body: flow.VendorQuoteIn, me: User = Depends(vendor_reader), db: Session = Depends(get_db)):
    """The vendor's quotation design (intro, terms, payment terms, validity), shown with its options."""
    _vendor(me, "vendor.quote_design")
    partner = db.get(Partner, me.partner_id)
    partner.quote_settings = body.model_dump()
    db.commit()
    return body


@router.get("/api/partner/stats")
def partner_stats(me: User = Depends(get_partner_user), db: Session = Depends(get_db)):
    """The account's own figures: requests or jobs by status, money, trips ahead and payments due."""
    need = "client.reports" if me.partner.kind == PartnerKind.CLIENT else "vendor.history"
    if need not in effective_features(me.partner):
        raise HTTPException(403, "This service is not switched on for your account")
    return flow.partner_stats(db, me)
