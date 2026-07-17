"""Suppliers registry endpoints (issue #129).

Mirrors the products catalogue: list for any authenticated user, create for
owner/admin, duplicate active name returns 409.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cocina_control.api.deps import get_current_user, require_any_role
from cocina_control.db import get_session
from cocina_control.models.supplier import Supplier
from cocina_control.models.user import User
from cocina_control.schemas.supplier import (
    SupplierCreate,
    SupplierListItem,
    SupplierResponse,
)

router = APIRouter(prefix="/suppliers", tags=["suppliers"])

_NAME_UNIQUE_CONSTRAINT = "ix_suppliers_name_active_unique"


@router.get(
    "",
    response_model=list[SupplierListItem],
    summary="List active suppliers",
)
def list_suppliers(
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
) -> list[Supplier]:
    """Return all active suppliers ordered alphabetically by name."""
    stmt = (
        select(Supplier)
        .where(Supplier.is_active.is_(True))
        .order_by(Supplier.name)
    )
    return list(session.scalars(stmt).all())


@router.post(
    "",
    response_model=SupplierResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a supplier",
)
def create_supplier(
    body: SupplierCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_any_role("owner", "admin")),
) -> Supplier:
    """Create a new supplier in the registry.

    - name is normalised to UPPER CASE (internal whitespace collapsed) by the schema.
    - phone is optional free text (max 30 chars).
    - Duplicate name among active suppliers returns 409.
    """
    existing = session.scalar(
        select(Supplier).where(
            Supplier.name == body.name,
            Supplier.is_active.is_(True),
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Supplier name already exists",
        )

    supplier = Supplier(
        id=uuid.uuid4(),
        name=body.name,
        phone=body.phone,
        is_active=True,
        created_by=current_user.id,
    )
    session.add(supplier)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        if _NAME_UNIQUE_CONSTRAINT in str(exc.orig):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Supplier name already exists",
            ) from exc
        raise

    return supplier
