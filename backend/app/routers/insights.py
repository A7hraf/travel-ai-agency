"""AI insights: a company's own page (``/api/insights``) and the platform owner's view (``/api/system/insights``)."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..addons import grant, use, user_may
from ..database import get_db
from ..deps import require_permission, require_system_admin
from ..models import Company, InsightReport, User
from ..ratelimit import limiter
from ..services import insights as svc

router = APIRouter(tags=["insights"])


class ReportOut(BaseModel):
    id: int
    language: str
    content: str
    created_by: str | None
    created_at: datetime


class InsightsOut(BaseModel):
    metrics: dict
    report: ReportOut | None


class ReportIn(BaseModel):
    language: Literal["en", "ar"] = "en"


def _report(r: InsightReport | None) -> ReportOut | None:
    return ReportOut(id=r.id, language=r.language, content=r.content, created_by=r.created_by,
                     created_at=r.created_at) if r else None


def reader(user: User = Depends(require_permission("reports.view"))) -> User:
    if not user_may(user, "insights"):
        raise HTTPException(403, "AI insights are not switched on for your company. Ask the platform admin.")
    return user


@router.get("/api/insights", response_model=InsightsOut)
def company_insights(days: int = 90, me: User = Depends(reader), db: Session = Depends(get_db)):
    days = max(7, min(days, 365))
    metrics = svc.for_levels(svc.company_metrics(db, me.company, days), grant(me.company, "insights").levels)
    return InsightsOut(metrics=metrics, report=_report(svc.latest_report(db, me.company_id, "company")))


@router.post("/api/insights/report", response_model=ReportOut)
def company_report(body: ReportIn, me: User = Depends(reader), db: Session = Depends(get_db)):
    limiter.check(f"insights-report:{me.company_id}", 6, "You can ask for a new report a few times per hour", window=3600)
    use(db, me, "insights")
    metrics = svc.for_levels(svc.company_metrics(db, me.company, 90), grant(me.company, "insights").levels)
    return _report(svc.write_report(db, metrics, "company", body.language, me.company, me.full_name))


# --- Platform owner -----------------------------------------------------------------------------------

@router.get("/api/system/insights", response_model=InsightsOut)
def owner_insights(_: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    return InsightsOut(metrics=svc.platform_overview(db), report=_report(svc.latest_report(db, None, "owner")))


@router.post("/api/system/insights/report", response_model=ReportOut)
def owner_report(body: ReportIn, me: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    limiter.check("insights-report:owner", 10, "You can ask for a new report a few times per hour", window=3600)
    return _report(svc.write_report(db, svc.platform_overview(db), "owner", body.language, None, me.full_name))


@router.get("/api/system/companies/{company_id}/insights", response_model=InsightsOut)
def owner_company_insights(company_id: int, _: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    """The owner looks at one company's figures (without its customers' words), to advise or sell to it."""
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "Company not found")
    return InsightsOut(metrics=svc.company_metrics(db, company, 90, private=False),
                       report=_report(svc.latest_report(db, company_id, "company")))
