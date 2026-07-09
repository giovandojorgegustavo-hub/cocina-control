"""CSV export service for the dashboard (issue #14).

Generates a UTF-8 BOM CSV stream with all forensic events in the given date range.
Uses a Python generator so that FastAPI's StreamingResponse can flush rows
without loading all events into memory at once.

CSV columns:
  event_type, event_id, date, operator_name, product_id, product_name,
  qty, announced_qty, delivery_id, delivery_order_id, count_id, corrects_id, reason

  For delivery_item rows:
    qty           = received_qty (or announced_qty fallback)
    announced_qty = the originally announced quantity
  For all other event types:
    qty           = the event quantity
    announced_qty = empty

Content-Type : text/csv; charset=utf-8
BOM          : \\xef\\xbb\\xbf  (Excel requires BOM to detect UTF-8 correctly)

The CSV includes ALL rows — originals AND corrections — because the export
is a forensic document.  Consumers who want the reconciled state must filter
to the leaf chain (items without a corrector) in Excel or a downstream tool.

Type filter (query param `type`):
  all      — all three event types (default)
  delivery — delivery_items only
  order    — delivery_order_items only
  count    — inventory_count_items only

Security:
  Text-free fields (product_name, operator_name, reason) are sanitized against
  CSV formula injection (fields starting with =, +, -, @, \\t, \\r are prefixed
  with a single quote so that spreadsheet applications treat them as text).
"""

import csv
import io
import uuid
from collections.abc import Generator
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from cocina_control.models.delivery import Delivery, DeliveryItem
from cocina_control.models.delivery_order import DeliveryOrder, DeliveryOrderItem
from cocina_control.models.inventory import InventoryCount, InventoryCountItem
from cocina_control.models.product import Product
from cocina_control.models.user import User

_CSV_COLUMNS = [
    "event_type",
    "event_id",
    "date",
    "operator_name",
    "product_id",
    "product_name",
    "qty",
    "announced_qty",
    "delivery_id",
    "delivery_order_id",
    "count_id",
    "corrects_id",
    "reason",
]

_VALID_TYPES = {"all", "delivery", "order", "count"}

# Characters that cause spreadsheet applications (Excel, LibreOffice) to
# interpret cell content as a formula.  Fields starting with any of these are
# prefixed with a single quote to force plain-text treatment.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _str(v: object) -> str:
    """Convert value to string, '' for None."""
    if v is None:
        return ""
    return str(v)


def _sanitize_csv_field(value: str | None) -> str:
    """Neutralize CSV formula-injection payloads.

    Any text-free field whose first character could trigger formula evaluation
    in a spreadsheet is prefixed with a single quote.  The quote is rendered
    inside the CSV cell and is visible in the raw file, which is the standard
    safe-export convention (OWASP CSV Injection).
    """
    if not value:
        return ""
    if value[0] in _FORMULA_PREFIXES:
        return "'" + value
    return value


def _collect_rows(
    session: Session,
    from_dt: datetime,
    to_dt: datetime,
    event_type_filter: str,
) -> list[dict]:
    """Collect all event rows for the given range and type filter.

    Returned as a list of dicts keyed by _CSV_COLUMNS.
    """
    rows: list[dict] = []

    # ---- build lookup maps ----
    # Products.
    all_products = {p.id: p for p in session.scalars(select(Product)).all()}
    # Users.
    all_users = {u.id: u for u in session.scalars(select(User)).all()}

    def product_name(pid: uuid.UUID) -> str:
        p = all_products.get(pid)
        return p.name if p else _str(pid)

    def operator_name(uid: uuid.UUID) -> str:
        u = all_users.get(uid)
        return u.name if u else _str(uid)

    # ---- delivery_items ----
    if event_type_filter in ("all", "delivery"):
        validated_deliveries = session.scalars(
            select(Delivery).where(
                Delivery.status == "validada",
                Delivery.validated_at >= from_dt,
                Delivery.validated_at <= to_dt,
            )
        ).all()
        delivery_ids = {d.id for d in validated_deliveries}

        items_from_deliveries: list[DeliveryItem] = (
            session.scalars(
                select(DeliveryItem).where(
                    DeliveryItem.delivery_id.in_(delivery_ids)
                )
            ).all()
            if delivery_ids
            else []
        )
        items_created_in_range: list[DeliveryItem] = session.scalars(
            select(DeliveryItem).where(
                DeliveryItem.created_at >= from_dt,
                DeliveryItem.created_at <= to_dt,
            )
        ).all()

        seen: set[uuid.UUID] = set()
        for item in list(items_from_deliveries) + list(items_created_in_range):
            if item.id in seen:
                continue
            seen.add(item.id)
            qty = item.received_qty if item.received_qty is not None else item.announced_qty
            rows.append({
                "event_type": "delivery_item",
                "event_id": _str(item.id),
                "date": _str(item.created_at),
                "operator_name": _sanitize_csv_field(operator_name(item.created_by)),
                "product_id": _str(item.product_id),
                "product_name": _sanitize_csv_field(product_name(item.product_id)),
                "qty": _str(qty),
                "announced_qty": _str(item.announced_qty),
                "delivery_id": _str(item.delivery_id),
                "delivery_order_id": "",
                "count_id": "",
                "corrects_id": _str(item.corrects_id),
                "reason": _sanitize_csv_field(_str(item.reason)),
            })

    # ---- delivery_order_items ----
    if event_type_filter in ("all", "order"):
        completed_orders = session.scalars(
            select(DeliveryOrder).where(
                DeliveryOrder.status == "completed",
                DeliveryOrder.completed_at >= from_dt,
                DeliveryOrder.completed_at <= to_dt,
            )
        ).all()
        order_ids = {o.id for o in completed_orders}

        order_items_from_completed: list[DeliveryOrderItem] = (
            session.scalars(
                select(DeliveryOrderItem).where(
                    DeliveryOrderItem.delivery_order_id.in_(order_ids)
                )
            ).all()
            if order_ids
            else []
        )
        order_items_in_range: list[DeliveryOrderItem] = session.scalars(
            select(DeliveryOrderItem).where(
                DeliveryOrderItem.created_at >= from_dt,
                DeliveryOrderItem.created_at <= to_dt,
            )
        ).all()

        seen_order: set[uuid.UUID] = set()
        for item in list(order_items_from_completed) + list(order_items_in_range):
            if item.id in seen_order:
                continue
            seen_order.add(item.id)
            rows.append({
                "event_type": "delivery_order_item",
                "event_id": _str(item.id),
                "date": _str(item.created_at),
                "operator_name": _sanitize_csv_field(operator_name(item.created_by)),
                "product_id": _str(item.product_id),
                "product_name": _sanitize_csv_field(product_name(item.product_id)),
                "qty": _str(item.quantity),
                "announced_qty": "",
                "delivery_id": "",
                "delivery_order_id": _str(item.delivery_order_id),
                "count_id": "",
                "corrects_id": _str(item.corrects_id),
                "reason": "",
            })

    # ---- inventory_count_items ----
    if event_type_filter in ("all", "count"):
        completed_counts = session.scalars(
            select(InventoryCount).where(
                InventoryCount.status == "completed",
                InventoryCount.completed_at >= from_dt,
                InventoryCount.completed_at <= to_dt,
            )
        ).all()
        count_ids = {c.id for c in completed_counts}

        count_items_from_completed: list[InventoryCountItem] = (
            session.scalars(
                select(InventoryCountItem).where(
                    InventoryCountItem.inventory_count_id.in_(count_ids)
                )
            ).all()
            if count_ids
            else []
        )
        count_items_in_range: list[InventoryCountItem] = session.scalars(
            select(InventoryCountItem).where(
                InventoryCountItem.created_at >= from_dt,
                InventoryCountItem.created_at <= to_dt,
            )
        ).all()

        seen_count: set[uuid.UUID] = set()
        for item in list(count_items_from_completed) + list(count_items_in_range):
            if item.id in seen_count:
                continue
            seen_count.add(item.id)
            rows.append({
                "event_type": "inventory_count_item",
                "event_id": _str(item.id),
                "date": _str(item.created_at),
                "operator_name": _sanitize_csv_field(operator_name(item.created_by)),
                "product_id": _str(item.product_id),
                "product_name": _sanitize_csv_field(product_name(item.product_id)),
                "qty": _str(item.quantity),
                "announced_qty": "",
                "delivery_id": "",
                "delivery_order_id": "",
                "count_id": _str(item.inventory_count_id),
                "corrects_id": _str(item.corrects_id),
                "reason": _sanitize_csv_field(_str(item.reason)),
            })

    # Sort all rows by date ascending.
    rows.sort(key=lambda r: r["date"])
    return rows


def generate_csv(
    session: Session,
    from_dt: datetime,
    to_dt: datetime,
    event_type_filter: str = "all",
) -> Generator[bytes, None, None]:
    """Yield CSV chunks as bytes.

    First chunk: UTF-8 BOM + header row.
    Subsequent chunks: one row per event.

    The generator materialises all rows in memory before streaming because
    the DB session is bound to the request and cannot be used lazily after
    the response starts.  For v0.1 volumes (< 10k rows) this is fine.
    """
    if event_type_filter not in _VALID_TYPES:
        raise ValueError(
            f"Invalid export type '{event_type_filter}'. "
            f"Valid values: {sorted(_VALID_TYPES)}"
        )

    rows = _collect_rows(session, from_dt, to_dt, event_type_filter)

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_COLUMNS, lineterminator="\r\n")

    # BOM + header.
    bom = "﻿"
    buf.write(bom)
    writer.writeheader()
    yield buf.getvalue().encode("utf-8")

    # Data rows, one at a time.
    for row in rows:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=_CSV_COLUMNS, lineterminator="\r\n")
        writer.writerow(row)
        yield buf.getvalue().encode("utf-8")
