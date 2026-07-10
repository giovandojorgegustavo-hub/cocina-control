"""Dashboard endpoints (issue #14 — tablero del dueño).

Endpoints
---------
GET /api/v1/dashboard/summary               — stock, consumption, alerts, low stock
GET /api/v1/dashboard/traceability/{id}     — all events for one product
GET /api/v1/dashboard/export                — CSV download of all events

Access control
--------------
ALL endpoints are owner-only.  Any request from an operator (or unauthenticated)
receives 401 or 403 before any query runs.

Date parameters
---------------
Query params `from` and `to` are required ISO dates (YYYY-MM-DD) interpreted as
the business timezone (default America/Lima; configurable via COCINA_BUSINESS_TIMEZONE):
  - from → 00:00:00.000000 local time (beginning of day)
  - to   → 23:59:59.999999 local time (end of day)

This conversion is done in this module so that callers (tests and production)
always provide wall-clock dates as the dueño sees them on the calendar.

Naming note: `from` is a Python reserved word; FastAPI accepts it as a query
parameter via Query(..., alias="from").
"""

import uuid
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from cocina_control.api.deps import require_role
from cocina_control.config import get_settings
from cocina_control.db import get_session
from cocina_control.models.product import Product
from cocina_control.models.user import User
from cocina_control.schemas.dashboard import DashboardSummaryResponse, TraceabilityEvent
from cocina_control.services.dashboard import compute_summary, compute_traceability
from cocina_control.services.export import _VALID_TYPES, generate_csv

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _range_to_utc(from_date: date, to_date: date) -> tuple[datetime, datetime]:
    """Convert a from/to date pair (business local time) to UTC-aware datetimes.

    from_dt = from_date at 00:00:00.000000 in the business timezone
    to_dt   = to_date  at 23:59:59.999999 in the business timezone

    The business timezone is configured via COCINA_BUSINESS_TIMEZONE
    (default America/Lima).
    """
    tz = ZoneInfo(get_settings().business_timezone)
    from_dt = datetime.combine(from_date, time(0, 0, 0, 0), tzinfo=tz)
    to_dt = datetime.combine(to_date, time(23, 59, 59, 999999), tzinfo=tz)
    return from_dt, to_dt


# ---------------------------------------------------------------------------
# GET /dashboard/summary
# ---------------------------------------------------------------------------


@router.get(
    "/summary",
    response_model=DashboardSummaryResponse,
    summary="Dashboard summary: stock, consumption, alerts, low stock (owner only)",
)
def get_summary(
    from_date: date = Query(..., alias="from", description="Start date YYYY-MM-DD (business tz)"),
    to_date: date = Query(..., alias="to", description="End date YYYY-MM-DD (business tz)"),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role("owner")),
) -> DashboardSummaryResponse:
    """Compute the dashboard summary for the requested date range.

    For each active product returns:
    - stock_now       — current stock (last count + entries − orders since last count)
    - entries_qty     — sum of validated deliveries in range
    - consumption     — period consumption (null if no prior count)
    - consumption_available — whether consumption can be calculated
    - alert           — true when numbers are mathematically impossible

    Also returns the list of products below their low_stock_threshold and a
    count of orders (completed vs photo-only) in the range.

    Dates are interpreted as the business timezone (default America/Lima;
    configurable via COCINA_BUSINESS_TIMEZONE).
    """
    if from_date > to_date:
        raise HTTPException(
            status_code=400,
            detail="'from' date must be on or before 'to' date",
        )
    from_dt, to_dt = _range_to_utc(from_date, to_date)
    return compute_summary(session, from_dt, to_dt)


# ---------------------------------------------------------------------------
# GET /dashboard/traceability/{product_id}
# ---------------------------------------------------------------------------


@router.get(
    "/traceability/{product_id}",
    response_model=list[TraceabilityEvent],
    summary="All events for a product in the date range (owner only)",
)
def get_traceability(
    product_id: uuid.UUID,
    from_date: date = Query(..., alias="from", description="Start date YYYY-MM-DD (business tz)"),
    to_date: date = Query(..., alias="to", description="End date YYYY-MM-DD (business tz)"),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role("owner")),
) -> list[TraceabilityEvent]:
    """Return every event (delivery, order, count) that touched a product in the range.

    Includes original rows AND corrections so the owner can reconstruct the
    full forensic chain using the `corrects_id` field.

    Results are ordered by date ASC.

    Returns 404 if the product does not exist (active or inactive).
    """
    if from_date > to_date:
        raise HTTPException(
            status_code=400,
            detail="'from' date must be on or before 'to' date",
        )

    # 404 if product does not exist.
    product = session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    from_dt, to_dt = _range_to_utc(from_date, to_date)
    return compute_traceability(session, product_id, from_dt, to_dt)


# ---------------------------------------------------------------------------
# GET /dashboard/export
# ---------------------------------------------------------------------------


@router.get(
    "/export",
    summary="Download CSV of all events in the date range (owner only)",
    response_class=StreamingResponse,
)
def export_csv(
    from_date: date = Query(..., alias="from", description="Start date YYYY-MM-DD (business tz)"),
    to_date: date = Query(..., alias="to", description="End date YYYY-MM-DD (business tz)"),
    type: str = Query("all", description="Filter: all | delivery | order | count"),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role("owner")),
) -> StreamingResponse:
    """Stream a UTF-8 BOM CSV with all events in the date range.

    Columns:
      event_type, event_id, date, operator_name, product_id, product_name,
      qty, delivery_id, delivery_order_id, count_id, corrects_id, reason

    The CSV includes ALL rows — originals and corrections — so the owner can
    reconstruct the full forensic chain in Excel.

    Query param `type` filters by event type:
      all      (default) — all three types
      delivery — delivery_items only
      order    — delivery_order_items only
      count    — inventory_count_items only

    Content-Type: text/csv; charset=utf-8
    Content-Disposition: attachment; filename="cocina-control_{from}_{to}.csv"
    """
    if from_date > to_date:
        raise HTTPException(
            status_code=400,
            detail="'from' date must be on or before 'to' date",
        )

    if type not in _VALID_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid 'type' value '{type}'. Valid values: {sorted(_VALID_TYPES)}",
        )

    from_dt, to_dt = _range_to_utc(from_date, to_date)
    filename = f"cocina-control_{from_date}_{to_date}.csv"
    generator = generate_csv(session, from_dt, to_dt, event_type_filter=type)

    return StreamingResponse(
        generator,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
