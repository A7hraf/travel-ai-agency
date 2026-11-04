"""CSV downloads (customers, bookings, payments) that are safe to open in Excel or Google Sheets.

A cell starting with = + - @ (or a tab / carriage return) could run as a formula in a spreadsheet,
so such text cells get a leading apostrophe. Numbers written by the server are left as they are.
"""

import csv
import io
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from decimal import Decimal

from fastapi.responses import Response

from .timeutil import business_tz

FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float, Decimal)):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(business_tz()).strftime("%Y-%m-%d %H:%M")
    if isinstance(value, date):
        return value.isoformat()
    text = str(value)
    return "'" + text if text.startswith(FORMULA_START) else text


def csv_response(filename: str, header: Sequence[str], rows: Iterable[Sequence]) -> Response:
    buf = io.StringIO()
    # A byte order mark so Excel opens Arabic names correctly.
    buf.write("﻿")
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow([safe_cell(h) for h in header])
    for row in rows:
        writer.writerow([safe_cell(v) for v in row])
    return Response(
        content=buf.getvalue().encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
