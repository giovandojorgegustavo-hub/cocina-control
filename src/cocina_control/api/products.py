"""Product catalogue endpoints.

Routes
------
GET    /api/v1/products           — list active products (owner + operator)
POST   /api/v1/products           — create product (owner only)
PATCH  /api/v1/products/{id}      — update product (owner only)
DELETE /api/v1/products/{id}      — soft-delete product (owner only)

Invariants
----------
- Products are never physically deleted; is_active is set to false.
- Name uniqueness is enforced only among active products (partial unique index).
- name is always stored in UPPER CASE.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from cocina_control.api.deps import get_current_user, require_role
from cocina_control.db import get_session
from cocina_control.models.product import Product
from cocina_control.models.user import User
from cocina_control.schemas.product import (
    ProductCreate,
    ProductListItem,
    ProductResponse,
    ProductUpdate,
)

router = APIRouter(prefix="/products", tags=["products"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_active_product_or_404(session: Session, product_id: uuid.UUID) -> Product:
    """Return the product by id. Raises 404 if it does not exist."""
    product = session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


def _assert_name_not_taken(
    session: Session,
    name: str,
    exclude_id: uuid.UUID | None = None,
) -> None:
    """Raise 409 if an active product with the given name already exists.

    exclude_id lets PATCH skip the product being edited (so a no-op rename
    on the same product does not trigger a false conflict).
    """
    stmt = select(Product).where(
        Product.name == name,
        Product.is_active.is_(True),
    )
    if exclude_id is not None:
        stmt = stmt.where(Product.id != exclude_id)

    existing = session.scalars(stmt).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An active product named '{name}' already exists",
        )


# ---------------------------------------------------------------------------
# GET /products
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=list[ProductListItem],
    summary="List active products",
)
def list_products(
    session: Annotated[Session, Depends(get_session)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> list[Product]:
    """Return all active products ordered alphabetically by name."""
    stmt = (
        select(Product)
        .where(Product.is_active.is_(True))
        .order_by(Product.name)
    )
    return list(session.scalars(stmt).all())


# ---------------------------------------------------------------------------
# POST /products
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a product",
)
def create_product(
    body: ProductCreate,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("owner"))],
) -> Product:
    """Create a new product in the catalogue.

    - name is normalised to UPPER CASE by the schema before reaching here.
    - Duplicate name among active products returns 409.
    """
    _assert_name_not_taken(session, body.name)

    product = Product(
        id=uuid.uuid4(),
        name=body.name,
        unit=body.unit.value,
        low_stock_threshold=body.low_stock_threshold,
        is_active=True,
        created_by=current_user.id,
    )
    session.add(product)
    session.flush()
    return product


# ---------------------------------------------------------------------------
# PATCH /products/{product_id}
# ---------------------------------------------------------------------------


@router.patch(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Update a product",
)
def update_product(
    product_id: uuid.UUID,
    body: ProductUpdate,
    session: Annotated[Session, Depends(get_session)],
    _current_user: Annotated[User, Depends(require_role("owner"))],
) -> Product:
    """Partially update a product.

    - Only active products can be edited; 409 if the product is inactive.
    - If name changes, checks for collision with other active products.
    """
    product = _get_active_product_or_404(session, product_id)

    if not product.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="product is inactive",
        )

    if body.name is not None and body.name != product.name:
        _assert_name_not_taken(session, body.name, exclude_id=product_id)
        product.name = body.name

    if body.unit is not None:
        product.unit = body.unit.value

    if body.low_stock_threshold is not None:
        product.low_stock_threshold = body.low_stock_threshold

    session.flush()
    return product


# ---------------------------------------------------------------------------
# DELETE /products/{product_id}
# ---------------------------------------------------------------------------


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate a product",
)
def delete_product(
    product_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    _current_user: Annotated[User, Depends(require_role("owner"))],
) -> None:
    """Soft-delete a product by setting is_active = false.

    Returns 409 if the product is already inactive.
    The row is never physically removed from the database.
    """
    product = _get_active_product_or_404(session, product_id)

    if not product.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="already inactive",
        )

    product.is_active = False
    session.flush()
