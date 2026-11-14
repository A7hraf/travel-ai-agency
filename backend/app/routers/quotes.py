"""Branded quotations (the design, and a request's draft or final quotation) and business reports."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..addons import require_addon
from ..audit import audit
from ..database import get_db
from ..deps import require_permission
from ..models import Ticket, User
from ..ratelimit import limiter
from ..services import quotes, reports
from ..timeutil import local_today

router = APIRouter(tags=["quotations and reports"])


# --- The quotation design -------------------------------------------------------------------------------

@router.get("/api/quote-settings", response_model=quotes.QuoteSettings)
def get_design(me: User = Depends(require_permission("tickets.view"))):
    require_addon(me.company, "quotes")
    return quotes.settings_of(me.company)


@router.put("/api/quote-settings", response_model=quotes.QuoteSettings)
def save_design(body: quotes.QuoteSettings, me: User = Depends(require_permission("settings.manage")),
                db: Session = Depends(get_db)):
    require_addon(me.company, "quotes")
    clean = body.cleaned()
    me.company.quote_settings = clean.model_dump()
    audit(db, me, "quote_settings.saved")
    db.commit()
    return clean


class SampleIn(BaseModel):
    text: str = Field(min_length=20, max_length=12000)


@router.post("/api/quote-settings/ai-draft", response_model=quotes.QuoteSettings)
def design_from_sample(body: SampleIn, me: User = Depends(require_permission("settings.manage"))):
    """The owner pastes a sample quotation; the AI keeps its fixed text (introduction, terms, footer). Not saved."""
    require_addon(me.company, "quotes")
    limiter.check(f"quote-sample:{me.company_id}", 10, "The AI is busy: please try again in a few minutes", window=3600)
    return quotes.ai_draft(body.text, quotes.settings_of(me.company))


@router.get("/api/tickets/{ticket_id}/quotation")
def ticket_quotation(ticket_id: int, kind: Literal["draft", "final"] = "draft",
                     me: User = Depends(require_permission("tickets.view")), db: Session = Depends(get_db)):
    require_addon(me.company, "quotes")
    ticket = db.get(Ticket, ticket_id)
    if ticket is None or ticket.company_id != me.company_id:
        raise HTTPException(404, "Ticket not found")
    return quotes.quotation(db, me.company, ticket, kind)


# --- Reports --------------------------------------------------------------------------------------------

def _period(start: date | None, end: date | None) -> tuple[date, date]:
    end = end or local_today()
    start = start or end.replace(day=1)
    if start > end:
        raise HTTPException(422, "The start date is after the end date")
    if (end - start).days > 731:
        raise HTTPException(422, "A report can cover at most two years")
    return start, end


@router.get("/api/reports/summary")
def report(start: date | None = None, end: date | None = None, me: User = Depends(require_permission("reports.view")),
           db: Session = Depends(get_db)):
    require_addon(me.company, "reports")
    return reports.summary(db, me.company, *_period(start, end))


@router.get("/api/reports/summary.xlsx")
def report_excel(start: date | None = None, end: date | None = None,
                 me: User = Depends(require_permission("reports.view")), db: Session = Depends(get_db)):
    require_addon(me.company, "reports_excel")
    limiter.check(f"report-xlsx:{me.company_id}", 60, "Too many downloads, please wait a few minutes", window=3600)
    s, e = _period(start, end)
    data = reports.excel(db, me.company, s, e)
    name = f"report-{s.isoformat()}-{e.isoformat()}.xlsx"
    return Response(content=data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "private, no-store"})

