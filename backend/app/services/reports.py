"""Business reports for a period: requests, revenue, margin, quotations, services, staff, destinations and
suppliers. Shown as a branded page (printed to PDF by the browser) and downloadable as an Excel file."""

from __future__ import annotations

import io
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..addons import has_addon
from ..branding import public_branding
from ..models import Company, Ticket, TicketStatus as T

PAID = (T.PAID, T.CONFIRMED, T.COMPLETED)
QUOTED_LATER = (T.QUOTED, T.CHANGES, T.CHOSEN, T.FINAL, T.PENDING_PAYMENT, T.IN_PROGRESS, T.PAID, T.WORKING, T.CONFIRMED, T.COMPLETED, T.REJECTED)
APPROVED = (T.PENDING_PAYMENT, T.IN_PROGRESS, T.PAID, T.WORKING, T.CONFIRMED, T.COMPLETED)


def _money(v) -> float:
    return float(round(Decimal(v or 0), 3))


def tickets_in(db: Session, company_id: int, start: date, end: date) -> list[Ticket]:
    lo = datetime.combine(start, time.min, tzinfo=timezone.utc)
    hi = datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc)
    return list(db.scalars(select(Ticket).where(Ticket.company_id == company_id, Ticket.created_at >= lo,
                                                Ticket.created_at < hi)
                           .options(selectinload(Ticket.service), selectinload(Ticket.assigned_to),
                                    selectinload(Ticket.options), selectinload(Ticket.customer))
                           .order_by(Ticket.created_at)).all())


def summary(db: Session, company: Company, start: date, end: date) -> dict:
    tickets = tickets_in(db, company.id, start, end)
    paid = [t for t in tickets if t.status in PAID]
    revenue = sum((t.total_price for t in paid), Decimal(0))
    margin, margin_known = Decimal(0), 0
    for t in paid:
        chosen = [o for o in t.options if o.chosen]
        if chosen and all(o.cost_price is not None and o.price is not None for o in chosen):
            margin += sum((o.price - o.cost_price for o in chosen), Decimal(0))
            margin_known += 1
    by_service: dict[str, dict] = defaultdict(lambda: {"requests": 0, "confirmed": 0, "revenue": Decimal(0)})
    by_staff: dict[str, dict] = defaultdict(lambda: {"requests": 0, "confirmed": 0, "revenue": Decimal(0)})
    for t in tickets:
        key = t.service.name_en if t.service else "Holiday packages"
        for bucket in (by_service[key], by_staff[t.assigned_to.full_name if t.assigned_to else "—"]):
            bucket["requests"] += 1
            if t.status in PAID:
                bucket["confirmed"] += 1
                bucket["revenue"] += t.total_price
    service_ar = {t.service.name_en: t.service.name_ar for t in tickets if t.service}
    quoted = [t for t in tickets if t.quote_round or t.status in QUOTED_LATER and t.service and t.service.key != "packages"]
    approved = [t for t in quoted if t.status in APPROVED]
    destinations = Counter((t.destination or "").strip().title() for t in tickets if (t.destination or "").strip())
    out = {
        "start": start, "end": end, "currency": company.currency or "OMR",
        "company": {"name": company.name, "logo": public_branding(company).logo,
                    "primary": public_branding(company).primary_color},
        "totals": {"requests": len(tickets), "paid": len(paid), "revenue": _money(revenue),
                   "average_value": _money(revenue / len(paid)) if paid else None,
                   "margin": _money(margin) if margin_known else None, "margin_requests": margin_known,
                   "cancelled": sum(1 for t in tickets if t.status == T.CANCELLED),
                   "rejected": sum(1 for t in tickets if t.status == T.REJECTED),
                   "waiting_payment": _money(sum((t.total_price for t in tickets if t.status == T.PENDING_PAYMENT), Decimal(0)))},
        "by_status": dict(Counter(t.status for t in tickets)),
        "quotations": {"quoted": len(quoted), "approved": len(approved),
                       "approval_rate": round(len(approved) / len(quoted), 3) if quoted else None,
                       "average_rounds": round(sum(t.quote_round for t in quoted) / len(quoted), 2) if quoted else None},
        "by_service": [{"name_en": k, "name_ar": service_ar.get(k, k), **v, "revenue": _money(v["revenue"])}
                       for k, v in sorted(by_service.items(), key=lambda kv: -kv[1]["requests"])],
        "by_staff": [{"name": k, **v, "revenue": _money(v["revenue"])}
                     for k, v in sorted(by_staff.items(), key=lambda kv: -kv[1]["revenue"])],
        "destinations": destinations.most_common(8),
        "suppliers": None,
    }
    if has_addon(company, "library_analytics"):
        from .library import stats  # noqa: PLC0415

        days = max(7, (end - start).days + 1)
        out["suppliers"] = stats(db, company.id, days)["suppliers"][:8]
    return out


def excel(db: Session, company: Company, start: date, end: date) -> bytes:
    """The same report as an Excel workbook, in the company's colour."""
    from openpyxl import Workbook  # noqa: PLC0415
    from openpyxl.styles import Alignment, Font, PatternFill  # noqa: PLC0415

    data = summary(db, company, start, end)
    color = (data["company"]["primary"] or "#0088b0").lstrip("#").upper()
    head_fill, head_font = PatternFill("solid", fgColor=color), Font(bold=True, color="FFFFFF")
    wb = Workbook()

    def sheet(ws, title: str, header: list[str], rows: list[list]):
        ws.title = title
        ws.append([f"{company.name} · {title}"])
        ws["A1"].font = Font(bold=True, size=14, color=color)
        ws.append([f"{start.isoformat()} → {end.isoformat()} · {data['currency']}"])
        ws.append([])
        ws.append(header)
        for cell in ws[4]:
            cell.fill, cell.font = head_fill, head_font
            cell.alignment = Alignment(vertical="center")
        for r in rows:
            ws.append(r)
        for col in ws.columns:
            width = max(len(str(c.value or "")) for c in list(col)[3:]) if ws.max_row > 3 else 10
            ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 10), 48)
        ws.freeze_panes = "A5"

    t = data["totals"]
    sheet(wb.active, "Summary", ["Figure", "Value"], [
        ["Requests", t["requests"]], ["Paid or confirmed", t["paid"]], ["Revenue", t["revenue"]],
        ["Average value", t["average_value"]], ["Margin (where costs are known)", t["margin"]],
        ["Waiting for payment", t["waiting_payment"]], ["Cancelled", t["cancelled"]], ["Rejected by clients", t["rejected"]],
        ["Quotations sent", data["quotations"]["quoted"]], ["Quotations approved", data["quotations"]["approved"]],
        ["Average quotation rounds", data["quotations"]["average_rounds"]]])
    sheet(wb.create_sheet(), "Requests",
          ["Reference", "Created", "Service", "Client", "Destination", "Departure", "Status", "Total", "Assigned to"],
          [[x.reference, x.created_at.date().isoformat(), x.service.name_en if x.service else "Holiday packages",
            x.lead_traveler_name or x.customer.name or "", x.destination or "", x.departure_date or "", x.status,
            _money(x.total_price), x.assigned_to.full_name if x.assigned_to else ""]
           for x in tickets_in(db, company.id, start, end)])
    sheet(wb.create_sheet(), "By service", ["Service", "Requests", "Paid or confirmed", "Revenue"],
          [[s["name_en"], s["requests"], s["confirmed"], s["revenue"]] for s in data["by_service"]])
    sheet(wb.create_sheet(), "By staff", ["Staff member", "Requests", "Paid or confirmed", "Revenue"],
          [[s["name"], s["requests"], s["confirmed"], s["revenue"]] for s in data["by_staff"]])
    if data["suppliers"]:
        sheet(wb.create_sheet(), "Suppliers", ["Supplier", "Part", "Bookings", "You paid", "Clients paid", "Margin"],
              [[s["name"], s["category"], s["bookings"], s["cost"], s["revenue"], s["margin"]] for s in data["suppliers"]])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
