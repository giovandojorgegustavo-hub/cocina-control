"""Esquema de fabricacion (migration 0017) — invariantes a nivel base de datos.

No testea endpoints (todavia no existen): testea que la BASE rechace los estados
imposibles. Cada CHECK, indice unico parcial y trigger de 0017 tiene su test aca,
porque son la ultima linea de defensa cuando el codigo de aplicacion falla.

Este es un ledger de auditoria: el operario que registra una fabricacion es la
persona a la que despues se le audita el faltante. Cada test de abajo cierra una
forma concreta de inflar el stock teorico y fabricar la coartada del faltante
propio. Los nombres dicen QUE abuso cierran, no que constraint tocan.

Los triggers de integridad del batch son DEFERRABLE INITIALLY DEFERRED (batch e
inputs se insertan en la misma transaccion). Los tests usan
`SET CONSTRAINTS ALL IMMEDIATE` para forzarlos, porque el fixture db_session
nunca commitea.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DatabaseError, IntegrityError

from cocina_control.models import (
    ManufacturingBatch,
    ManufacturingBatchEvent,
    ManufacturingBatchInput,
    ManufacturingRecipe,
    ManufacturingRecipeItem,
    ManufacturingRecipeVersion,
    Product,
    User,
)


def _immediate(session) -> None:
    """Fuerza los constraint triggers diferidos sin commitear.

    IMMEDIATE verifica lo pendiente y queda activo para el resto de la
    transaccion; hay que devolverlo a DEFERRED o el siguiente batch se valida
    antes de que existan sus insumos.
    """
    session.flush()
    session.execute(sa.text("SET CONSTRAINTS ALL IMMEDIATE"))
    session.execute(sa.text("SET CONSTRAINTS ALL DEFERRED"))


def _make_product(
    session,
    owner: User,
    name: str,
    *,
    is_purchase: bool = True,
    is_sale: bool = False,
    is_manufactured: bool = False,
) -> Product:
    product = Product(
        id=uuid.uuid4(),
        name=name,
        unit="kg",
        is_purchase=is_purchase,
        is_sale=is_sale,
        is_manufactured=is_manufactured,
        created_by=owner.id,
    )
    session.add(product)
    session.flush()
    return product


def _make_recipe(
    session, owner: User, output: Product, input_: Product, *, base: str = "1"
) -> tuple[ManufacturingRecipe, ManufacturingRecipeVersion]:
    recipe = ManufacturingRecipe(id=uuid.uuid4(), output_product_id=output.id, created_by=owner.id)
    session.add(recipe)
    session.flush()
    version = ManufacturingRecipeVersion(
        id=uuid.uuid4(),
        recipe_id=recipe.id,
        input_product_id=input_.id,
        base_input_qty=Decimal(base),
        default_input_qty=Decimal(base),
        created_by=owner.id,
    )
    session.add(version)
    session.flush()
    return recipe, version


def _make_batch(
    session,
    user: User,
    recipe: ManufacturingRecipe,
    version: ManufacturingRecipeVersion,
    primary: Product,
    *,
    input_qty: str = "1",
    output_qty: str = "22",
    measurement: str = "measured",
    validated_at: datetime | None = None,
    created_by: User | None = None,
) -> ManufacturingBatch:
    batch = ManufacturingBatch(
        id=uuid.uuid4(),
        recipe_id=recipe.id,
        recipe_version_id=version.id,
        output_product_id=recipe.output_product_id,
        output_qty=Decimal(output_qty),
        measurement=measurement,
        validated_at=validated_at or datetime.now(UTC),
        validated_by=user.id,
        created_by=(created_by or user).id,
    )
    session.add(batch)
    session.add(
        ManufacturingBatchInput(
            id=uuid.uuid4(),
            batch_id=batch.id,
            product_id=primary.id,
            qty=Decimal(input_qty),
            is_primary=True,
            created_by=user.id,
        )
    )
    _immediate(session)
    return batch


@pytest.fixture
def quinua(db_session, owner_user):
    return _make_product(db_session, owner_user, "quinua cruda")


@pytest.fixture
def cocida(db_session, owner_user):
    return _make_product(
        db_session, owner_user, "quinua cocida", is_purchase=False, is_manufactured=True
    )


# ---------------------------------------------------------------------------
# products.is_manufactured
# ---------------------------------------------------------------------------


def test_preparado_puede_no_comprarse_ni_venderse(db_session, cocida):
    """La quinua cocida no se compra ni se vende, pero existe y se cuenta."""
    assert cocida.is_manufactured is True


def test_producto_sin_ninguna_flag_es_rechazado(db_session, owner_user):
    with pytest.raises(IntegrityError) as exc:
        with db_session.begin_nested():
            _make_product(
                db_session,
                owner_user,
                "fantasma",
                is_purchase=False,
                is_sale=False,
                is_manufactured=False,
            )
    assert "ck_products_purchase_sale_or_manufactured" in str(exc.value)


# ---------------------------------------------------------------------------
# La coartada: acreditar produccion a otro producto
# ---------------------------------------------------------------------------


def test_no_se_puede_acreditar_produccion_a_otro_producto(
    db_session, owner_user, cocinero_user, quinua, cocida
):
    """El batch acredita al producto de SU receta. Antes era un campo libre:
    se podia fabricar quinua y acreditar 500 kg de lomo fino."""
    recipe, version = _make_recipe(db_session, owner_user, cocida, quinua)
    lomo = _make_product(db_session, owner_user, "lomo fino")

    with pytest.raises(IntegrityError) as exc:
        with db_session.begin_nested():
            db_session.add(
                ManufacturingBatch(
                    id=uuid.uuid4(),
                    recipe_id=recipe.id,
                    recipe_version_id=version.id,
                    output_product_id=lomo.id,  # <-- no es el de la receta
                    output_qty=Decimal("500"),
                    validated_at=datetime.now(UTC),
                    validated_by=cocinero_user.id,
                    created_by=cocinero_user.id,
                )
            )
            db_session.flush()
    assert "fk_manufacturing_batches_recipe_output" in str(exc.value)


def test_no_se_puede_usar_una_version_de_otra_receta(
    db_session, owner_user, cocinero_user, quinua, cocida
):
    """La version usada tiene que pertenecer a la receta declarada."""
    recipe_a, _ = _make_recipe(db_session, owner_user, cocida, quinua)
    lenteja = _make_product(db_session, owner_user, "lenteja cruda")
    lenteja_cocida = _make_product(
        db_session, owner_user, "lenteja cocida", is_purchase=False, is_manufactured=True
    )
    _, version_b = _make_recipe(db_session, owner_user, lenteja_cocida, lenteja)

    with pytest.raises(IntegrityError) as exc:
        with db_session.begin_nested():
            db_session.add(
                ManufacturingBatch(
                    id=uuid.uuid4(),
                    recipe_id=recipe_a.id,
                    recipe_version_id=version_b.id,  # <-- version ajena
                    output_product_id=recipe_a.output_product_id,
                    output_qty=Decimal("22"),
                    validated_at=datetime.now(UTC),
                    validated_by=cocinero_user.id,
                    created_by=cocinero_user.id,
                )
            )
            db_session.flush()
    assert "fk_manufacturing_batches_version_recipe" in str(exc.value)


def test_el_insumo_primario_tiene_que_ser_el_de_la_receta(
    db_session, owner_user, cocinero_user, quinua, cocida
):
    """Descontar el producto caro y reportar el rinde del barato: cerrado."""
    recipe, version = _make_recipe(db_session, owner_user, cocida, quinua)
    lomo = _make_product(db_session, owner_user, "lomo fino")

    with pytest.raises(DatabaseError) as exc:
        with db_session.begin_nested():
            _make_batch(db_session, cocinero_user, recipe, version, lomo)
    assert "no es el que declara la receta" in str(exc.value)


# ---------------------------------------------------------------------------
# Un peso, un lugar
# ---------------------------------------------------------------------------


def test_el_batch_no_guarda_el_peso_por_separado(db_session):
    """input_qty duplicaba el hecho: se reportaba rinde 22/1 mientras el
    inventario descontaba 6. El peso vive solo en el insumo primario."""
    cols = {c.name for c in ManufacturingBatch.__table__.columns}
    assert "input_qty" not in cols


def test_batch_sin_insumos_es_rechazado(db_session, owner_user, cocinero_user, quinua, cocida):
    """Un batch sin inputs crearia stock de la nada."""
    recipe, version = _make_recipe(db_session, owner_user, cocida, quinua)

    with pytest.raises(DatabaseError) as exc:
        with db_session.begin_nested():
            db_session.add(
                ManufacturingBatch(
                    id=uuid.uuid4(),
                    recipe_id=recipe.id,
                    recipe_version_id=version.id,
                    output_product_id=cocida.id,
                    output_qty=Decimal("22"),
                    validated_at=datetime.now(UTC),
                    validated_by=cocinero_user.id,
                    created_by=cocinero_user.id,
                )
            )
            _immediate(db_session)
    assert "exactamente un insumo primario" in str(exc.value)


def test_dos_insumos_primarios_son_rechazados(
    db_session, owner_user, cocinero_user, quinua, cocida
):
    recipe, version = _make_recipe(db_session, owner_user, cocida, quinua)
    batch = _make_batch(db_session, cocinero_user, recipe, version, quinua)
    sal = _make_product(db_session, owner_user, "sal")

    with pytest.raises(DatabaseError) as exc:
        with db_session.begin_nested():
            db_session.add(
                ManufacturingBatchInput(
                    id=uuid.uuid4(),
                    batch_id=batch.id,
                    product_id=sal.id,
                    qty=Decimal("15"),
                    is_primary=True,
                    created_by=cocinero_user.id,
                )
            )
            _immediate(db_session)
    assert "exactamente un insumo primario" in str(exc.value)


def test_corregir_un_extra_no_lo_puede_volver_primario(
    db_session, owner_user, cocinero_user, quinua, cocida
):
    """El indice parcial viejo filtraba corrects_id IS NULL: una correccion
    quedaba fuera del indice y podia declararse primaria."""
    recipe, version = _make_recipe(db_session, owner_user, cocida, quinua)
    batch = _make_batch(db_session, cocinero_user, recipe, version, quinua)
    sal = _make_product(db_session, owner_user, "sal")
    extra = ManufacturingBatchInput(
        id=uuid.uuid4(),
        batch_id=batch.id,
        product_id=sal.id,
        qty=Decimal("15"),
        is_primary=False,
        created_by=cocinero_user.id,
    )
    db_session.add(extra)
    _immediate(db_session)

    with pytest.raises(DatabaseError) as exc:
        with db_session.begin_nested():
            db_session.add(
                ManufacturingBatchInput(
                    id=uuid.uuid4(),
                    batch_id=batch.id,
                    product_id=sal.id,
                    qty=Decimal("15"),
                    is_primary=True,
                    corrects_id=extra.id,
                    reason="ajuste",
                    created_by=cocinero_user.id,
                )
            )
            _immediate(db_session)
    assert "exactamente un insumo primario" in str(exc.value)


def test_degradar_el_primario_deja_el_batch_sin_primario(
    db_session, owner_user, cocinero_user, quinua, cocida
):
    recipe, version = _make_recipe(db_session, owner_user, cocida, quinua)
    batch = _make_batch(db_session, cocinero_user, recipe, version, quinua)
    primary = db_session.execute(
        sa.select(ManufacturingBatchInput).where(ManufacturingBatchInput.batch_id == batch.id)
    ).scalar_one()

    with pytest.raises(DatabaseError) as exc:
        with db_session.begin_nested():
            db_session.add(
                ManufacturingBatchInput(
                    id=uuid.uuid4(),
                    batch_id=batch.id,
                    product_id=quinua.id,
                    qty=Decimal("1"),
                    is_primary=False,
                    corrects_id=primary.id,
                    reason="mal pesado",
                    created_by=cocinero_user.id,
                )
            )
            _immediate(db_session)
    assert "exactamente un insumo primario" in str(exc.value)


def test_insumo_repetido_en_un_batch_es_rechazado(
    db_session, owner_user, cocinero_user, quinua, cocida
):
    """Dos filas del mismo insumo descuentan doble del stock."""
    recipe, version = _make_recipe(db_session, owner_user, cocida, quinua)
    batch = _make_batch(db_session, cocinero_user, recipe, version, quinua)
    sal = _make_product(db_session, owner_user, "sal")
    for _ in range(1):
        db_session.add(
            ManufacturingBatchInput(
                id=uuid.uuid4(),
                batch_id=batch.id,
                product_id=sal.id,
                qty=Decimal("15"),
                created_by=cocinero_user.id,
            )
        )
    db_session.flush()

    with pytest.raises(IntegrityError) as exc:
        with db_session.begin_nested():
            db_session.add(
                ManufacturingBatchInput(
                    id=uuid.uuid4(),
                    batch_id=batch.id,
                    product_id=sal.id,
                    qty=Decimal("15"),
                    created_by=cocinero_user.id,
                )
            )
            db_session.flush()
    assert "uq_manufacturing_batch_inputs_root_per_product" in str(exc.value)


# ---------------------------------------------------------------------------
# Versionar una receta NO borra sus ingredientes
# ---------------------------------------------------------------------------


def test_versionar_la_receta_conserva_los_ingredientes(db_session, owner_user, quinua, cocida):
    """El bug silencioso: crear una v2 dejaba la receta sin items y
    mostaza/panko/huevo dejaban de descontarse para siempre."""
    recipe, v1 = _make_recipe(db_session, owner_user, cocida, quinua)
    panko = _make_product(db_session, owner_user, "panko")
    db_session.add(
        ManufacturingRecipeItem(
            id=uuid.uuid4(),
            recipe_id=recipe.id,
            product_id=panko.id,
            qty_per_base=Decimal("200"),
            created_by=owner_user.id,
        )
    )
    db_session.flush()

    db_session.add(
        ManufacturingRecipeVersion(
            id=uuid.uuid4(),
            recipe_id=recipe.id,
            input_product_id=quinua.id,
            base_input_qty=Decimal("2"),
            default_input_qty=Decimal("2"),
            corrects_id=v1.id,
            reason="ajuste de lote",
            created_by=owner_user.id,
        )
    )
    db_session.flush()

    items = db_session.execute(
        sa.select(sa.func.count())
        .select_from(ManufacturingRecipeItem)
        .where(ManufacturingRecipeItem.recipe_id == recipe.id)
    ).scalar_one()
    assert items == 1, "los ingredientes cuelgan de la identidad, no de la version"


def test_la_receta_no_puede_cambiar_de_producto_de_salida(db_session, owner_user, quinua, cocida):
    """output_product_id vive en la identidad y es UNIQUE: una cadena de
    correcciones ya no puede secuestrar la receta hacia otro preparado."""
    _make_recipe(db_session, owner_user, cocida, quinua)
    cols = {c.name for c in ManufacturingRecipeVersion.__table__.columns}
    assert "output_product_id" not in cols

    with pytest.raises(IntegrityError) as exc:
        with db_session.begin_nested():
            db_session.add(
                ManufacturingRecipe(
                    id=uuid.uuid4(), output_product_id=cocida.id, created_by=owner_user.id
                )
            )
            db_session.flush()
    assert "uq_manufacturing_recipes_output_product_id" in str(exc.value)


def test_una_sola_version_raiz_por_receta(db_session, owner_user, quinua, cocida):
    recipe, _ = _make_recipe(db_session, owner_user, cocida, quinua)
    with pytest.raises(IntegrityError) as exc:
        with db_session.begin_nested():
            db_session.add(
                ManufacturingRecipeVersion(
                    id=uuid.uuid4(),
                    recipe_id=recipe.id,
                    input_product_id=quinua.id,
                    base_input_qty=Decimal("1"),
                    default_input_qty=Decimal("1"),
                    created_by=owner_user.id,
                )
            )
            db_session.flush()
    assert "uq_manufacturing_recipe_versions_root_per_recipe" in str(exc.value)


def test_insumo_repetido_en_la_misma_receta_es_rechazado(db_session, owner_user, quinua, cocida):
    recipe, _ = _make_recipe(db_session, owner_user, cocida, quinua)
    sal = _make_product(db_session, owner_user, "sal")
    db_session.add(
        ManufacturingRecipeItem(
            id=uuid.uuid4(),
            recipe_id=recipe.id,
            product_id=sal.id,
            qty_per_base=Decimal("15"),
            created_by=owner_user.id,
        )
    )
    db_session.flush()
    with pytest.raises(IntegrityError) as exc:
        with db_session.begin_nested():
            db_session.add(
                ManufacturingRecipeItem(
                    id=uuid.uuid4(),
                    recipe_id=recipe.id,
                    product_id=sal.id,
                    qty_per_base=Decimal("2"),
                    created_by=owner_user.id,
                )
            )
            db_session.flush()
    assert "uq_manufacturing_recipe_items_root_per_product" in str(exc.value)


def test_una_correccion_sin_motivo_es_rechazada(db_session, owner_user, quinua, cocida):
    """requerimientos.md:244 — toda correccion lleva motivo."""
    recipe, v1 = _make_recipe(db_session, owner_user, cocida, quinua)
    with pytest.raises(IntegrityError) as exc:
        with db_session.begin_nested():
            db_session.add(
                ManufacturingRecipeVersion(
                    id=uuid.uuid4(),
                    recipe_id=recipe.id,
                    input_product_id=quinua.id,
                    base_input_qty=Decimal("2"),
                    default_input_qty=Decimal("2"),
                    corrects_id=v1.id,
                    reason=None,
                    created_by=owner_user.id,
                )
            )
            db_session.flush()
    assert "correction_needs_reason" in str(exc.value)


# ---------------------------------------------------------------------------
# Autoria y fecha
# ---------------------------------------------------------------------------


def test_no_se_puede_registrar_un_batch_a_nombre_de_otro(
    db_session, owner_user, cocinero_user, quinua, cocida
):
    """La bandeja muestra 'fabrico X': esa firma no puede ser un campo libre."""
    recipe, version = _make_recipe(db_session, owner_user, cocida, quinua)
    with pytest.raises(DatabaseError) as exc:
        with db_session.begin_nested():
            _make_batch(
                db_session,
                cocinero_user,
                recipe,
                version,
                quinua,
                created_by=owner_user,
            )
    assert "created_by y validated_by" in str(exc.value)


def test_no_se_puede_backdatear_un_batch(db_session, owner_user, cocinero_user, quinua, cocida):
    """Un batch retroactivo cambia el teorico de un periodo ya conciliado."""
    recipe, version = _make_recipe(db_session, owner_user, cocida, quinua)
    with pytest.raises(DatabaseError) as exc:
        with db_session.begin_nested():
            _make_batch(
                db_session,
                cocinero_user,
                recipe,
                version,
                quinua,
                validated_at=datetime.now(UTC) - timedelta(days=30),
            )
    assert "24 horas" in str(exc.value)


def test_no_se_puede_fechar_un_batch_en_el_futuro(
    db_session, owner_user, cocinero_user, quinua, cocida
):
    """Encabezaria la bandeja validated_at DESC para siempre."""
    recipe, version = _make_recipe(db_session, owner_user, cocida, quinua)
    with pytest.raises(DatabaseError) as exc:
        with db_session.begin_nested():
            _make_batch(
                db_session,
                cocinero_user,
                recipe,
                version,
                quinua,
                validated_at=datetime.now(UTC) + timedelta(days=365),
            )
    assert "futuro" in str(exc.value)


# ---------------------------------------------------------------------------
# Permisos
# ---------------------------------------------------------------------------


def test_el_cocinero_no_puede_crear_recetas(db_session, cocinero_user, quinua, cocida):
    """La unica asercion de permisos de la feature. Antes no existia."""
    with pytest.raises(DatabaseError) as exc:
        with db_session.begin_nested():
            db_session.add(
                ManufacturingRecipe(
                    id=uuid.uuid4(),
                    output_product_id=cocida.id,
                    created_by=cocinero_user.id,
                )
            )
            db_session.flush()
    assert "owner" in str(exc.value)


def test_el_cocinero_no_puede_anular_un_batch(
    db_session, owner_user, cocinero_user, quinua, cocida
):
    """Registrar es del cocinero; anular es del dueno."""
    recipe, version = _make_recipe(db_session, owner_user, cocida, quinua)
    batch = _make_batch(db_session, cocinero_user, recipe, version, quinua)
    with pytest.raises(DatabaseError) as exc:
        with db_session.begin_nested():
            db_session.add(
                ManufacturingBatchEvent(
                    id=uuid.uuid4(),
                    batch_id=batch.id,
                    event_type="annulled",
                    reason="cargado por error",
                    created_by=cocinero_user.id,
                )
            )
            db_session.flush()
    assert "owner" in str(exc.value)


def test_el_cocinero_si_puede_registrar_un_batch(
    db_session, owner_user, cocinero_user, quinua, cocida
):
    """Fabricar es del cocinero: es el punto de toda la feature."""
    recipe, version = _make_recipe(db_session, owner_user, cocida, quinua)
    batch = _make_batch(db_session, cocinero_user, recipe, version, quinua)
    assert batch.validated_by == cocinero_user.id
    assert batch.measurement == "measured"


# ---------------------------------------------------------------------------
# Append-only de verdad
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "table",
    [
        "manufacturing_recipes",
        "manufacturing_recipe_versions",
        "manufacturing_recipe_items",
        "manufacturing_batches",
        "manufacturing_batch_inputs",
        "manufacturing_batch_events",
    ],
)
def test_update_prohibido(db_session, owner_user, cocinero_user, quinua, cocida, table):
    """Un UPDATE reescribia la receta Y su autoria sin dejar rastro."""
    recipe, version = _make_recipe(db_session, owner_user, cocida, quinua)
    batch = _make_batch(db_session, cocinero_user, recipe, version, quinua)
    db_session.add(
        ManufacturingRecipeItem(
            id=uuid.uuid4(),
            recipe_id=recipe.id,
            product_id=quinua.id,
            qty_per_base=Decimal("5"),
            created_by=owner_user.id,
        )
    )
    db_session.add(
        ManufacturingBatchEvent(
            id=uuid.uuid4(),
            batch_id=batch.id,
            event_type="annulled",
            reason="prueba",
            created_by=owner_user.id,
        )
    )
    db_session.flush()

    with pytest.raises(DatabaseError) as exc:
        with db_session.begin_nested():
            db_session.execute(sa.text(f"UPDATE {table} SET created_at = now()"))
    assert "append-only" in str(exc.value)


@pytest.mark.parametrize(
    "table",
    ["manufacturing_recipe_items", "manufacturing_batch_inputs", "manufacturing_batches"],
)
def test_delete_prohibido(db_session, owner_user, cocinero_user, quinua, cocida, table):
    recipe, version = _make_recipe(db_session, owner_user, cocida, quinua)
    _make_batch(db_session, cocinero_user, recipe, version, quinua)
    db_session.add(
        ManufacturingRecipeItem(
            id=uuid.uuid4(),
            recipe_id=recipe.id,
            product_id=quinua.id,
            qty_per_base=Decimal("5"),
            created_by=owner_user.id,
        )
    )
    db_session.flush()

    with pytest.raises(DatabaseError) as exc:
        with db_session.begin_nested():
            db_session.execute(sa.text(f"DELETE FROM {table}"))
    assert "append-only" in str(exc.value)


# ---------------------------------------------------------------------------
# Anulacion
# ---------------------------------------------------------------------------


def test_un_batch_erroneo_se_puede_anular(db_session, owner_user, cocinero_user, quinua, cocida):
    """Sin anulacion, un '220 bolsitas' tipeado con un cero de mas infla el
    stock Y corre el umbral de deteccion del producto para siempre."""
    recipe, version = _make_recipe(db_session, owner_user, cocida, quinua)
    batch = _make_batch(db_session, cocinero_user, recipe, version, quinua, output_qty="220")
    event = ManufacturingBatchEvent(
        id=uuid.uuid4(),
        batch_id=batch.id,
        event_type="annulled",
        reason="se tipeo 220 en vez de 22",
        created_by=owner_user.id,
    )
    db_session.add(event)
    db_session.flush()
    assert event.created_by == owner_user.id


def test_un_batch_se_anula_una_sola_vez(db_session, owner_user, cocinero_user, quinua, cocida):
    recipe, version = _make_recipe(db_session, owner_user, cocida, quinua)
    batch = _make_batch(db_session, cocinero_user, recipe, version, quinua)
    db_session.add(
        ManufacturingBatchEvent(
            id=uuid.uuid4(),
            batch_id=batch.id,
            event_type="annulled",
            reason="error",
            created_by=owner_user.id,
        )
    )
    db_session.flush()
    with pytest.raises(IntegrityError) as exc:
        with db_session.begin_nested():
            db_session.add(
                ManufacturingBatchEvent(
                    id=uuid.uuid4(),
                    batch_id=batch.id,
                    event_type="annulled",
                    reason="otra vez",
                    created_by=owner_user.id,
                )
            )
            db_session.flush()
    assert "uq_manufacturing_batch_events_batch_type" in str(exc.value)


def test_anular_exige_motivo_no_vacio(db_session, owner_user, cocinero_user, quinua, cocida):
    recipe, version = _make_recipe(db_session, owner_user, cocida, quinua)
    batch = _make_batch(db_session, cocinero_user, recipe, version, quinua)
    with pytest.raises(IntegrityError) as exc:
        with db_session.begin_nested():
            db_session.add(
                ManufacturingBatchEvent(
                    id=uuid.uuid4(),
                    batch_id=batch.id,
                    event_type="annulled",
                    reason="   ",
                    created_by=owner_user.id,
                )
            )
            db_session.flush()
    assert "reason_not_blank" in str(exc.value)


# ---------------------------------------------------------------------------
# CHECKs de positividad y auto-correccion
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "constraint"),
    [
        ("base_input_qty", "ck_manufacturing_recipe_versions_base_input_qty_positive"),
        ("default_input_qty", "ck_manufacturing_recipe_versions_default_input_qty_positive"),
    ],
)
def test_cantidades_de_receta_deben_ser_positivas(
    db_session, owner_user, quinua, cocida, field, constraint
):
    """Una receta 'por 0 kg' hace que la regla de tres divida por cero."""
    recipe = ManufacturingRecipe(
        id=uuid.uuid4(), output_product_id=cocida.id, created_by=owner_user.id
    )
    db_session.add(recipe)
    db_session.flush()
    kwargs = {"base_input_qty": Decimal("1"), "default_input_qty": Decimal("1")}
    kwargs[field] = Decimal("0")
    with pytest.raises(IntegrityError) as exc:
        with db_session.begin_nested():
            db_session.add(
                ManufacturingRecipeVersion(
                    id=uuid.uuid4(),
                    recipe_id=recipe.id,
                    input_product_id=quinua.id,
                    created_by=owner_user.id,
                    **kwargs,
                )
            )
            db_session.flush()
    assert constraint in str(exc.value)


def test_output_qty_debe_ser_positiva(db_session, owner_user, cocinero_user, quinua, cocida):
    recipe, version = _make_recipe(db_session, owner_user, cocida, quinua)
    with pytest.raises(IntegrityError) as exc:
        with db_session.begin_nested():
            _make_batch(db_session, cocinero_user, recipe, version, quinua, output_qty="0")
    assert "ck_manufacturing_batches_output_qty_positive" in str(exc.value)


def test_qty_de_insumo_debe_ser_positiva(db_session, owner_user, cocinero_user, quinua, cocida):
    recipe, version = _make_recipe(db_session, owner_user, cocida, quinua)
    with pytest.raises(IntegrityError) as exc:
        with db_session.begin_nested():
            _make_batch(db_session, cocinero_user, recipe, version, quinua, input_qty="0")
    assert "ck_manufacturing_batch_inputs_qty_positive" in str(exc.value)


def test_una_fila_no_se_corrige_a_si_misma(db_session, owner_user, quinua, cocida):
    recipe, _ = _make_recipe(db_session, owner_user, cocida, quinua)
    row_id = uuid.uuid4()
    with pytest.raises(IntegrityError) as exc:
        with db_session.begin_nested():
            db_session.add(
                ManufacturingRecipeItem(
                    id=row_id,
                    recipe_id=recipe.id,
                    product_id=quinua.id,
                    qty_per_base=Decimal("5"),
                    corrects_id=row_id,
                    reason="loop",
                    created_by=owner_user.id,
                )
            )
            db_session.flush()
    assert "no_self_correction" in str(exc.value)


def test_rounding_integer_es_valido_para_el_huevo(db_session, owner_user, quinua, cocida):
    """El huevo es la unica unidad indivisible: se redondea y se guarda entero."""
    recipe, _ = _make_recipe(db_session, owner_user, cocida, quinua)
    huevo = _make_product(db_session, owner_user, "huevo")
    item = ManufacturingRecipeItem(
        id=uuid.uuid4(),
        recipe_id=recipe.id,
        product_id=huevo.id,
        qty_per_base=Decimal("4"),
        rounding="integer",
        created_by=owner_user.id,
    )
    db_session.add(item)
    db_session.flush()
    assert item.rounding == "integer"


# ---------------------------------------------------------------------------
# El rinde derivado — la razon de ser de toda la feature
# ---------------------------------------------------------------------------


def test_el_rinde_sale_de_los_batches_no_de_un_factor_declarado(
    db_session, owner_user, cocinero_user, quinua, cocida
):
    """1 kg -> 22 bolsitas. El factor se calcula, no se declara.

    Se calibra por (recipe_id, input_product_id), no por producto de salida:
    una version puede cambiar el insumo (pollo entero -> pechuga) y promediar
    kg con unidades da un numero sin significado.
    """
    recipe, version = _make_recipe(db_session, owner_user, cocida, quinua)
    _make_batch(db_session, cocinero_user, recipe, version, quinua, input_qty="1", output_qty="22")
    _make_batch(db_session, cocinero_user, recipe, version, quinua, input_qty="2", output_qty="46")

    # El peso de referencia es el insumo primario HOJA: hay que resolver la
    # cadena de corrects_id o una correccion cuenta dos veces.
    correction = sa.orm.aliased(ManufacturingBatchInput)
    primary = (
        sa.select(
            ManufacturingBatchInput.batch_id.label("batch_id"),
            ManufacturingBatchInput.qty.label("input_qty"),
        )
        .where(ManufacturingBatchInput.is_primary.is_(True))
        .where(
            ~sa.select(correction.id)
            .where(correction.corrects_id == ManufacturingBatchInput.id)
            .exists()
        )
        .subquery()
    )
    rinde = db_session.execute(
        sa.select(sa.func.avg(ManufacturingBatch.output_qty / primary.c.input_qty))
        .select_from(ManufacturingBatch)
        .join(primary, primary.c.batch_id == ManufacturingBatch.id)
        .join(
            ManufacturingRecipeVersion,
            ManufacturingRecipeVersion.id == ManufacturingBatch.recipe_version_id,
        )
        .where(ManufacturingBatch.recipe_id == recipe.id)
        .where(ManufacturingRecipeVersion.input_product_id == quinua.id)
        .where(ManufacturingBatch.measurement == "measured")
        .where(
            ~sa.select(ManufacturingBatchEvent.id)
            .where(ManufacturingBatchEvent.batch_id == ManufacturingBatch.id)
            .where(ManufacturingBatchEvent.event_type == "annulled")
            .exists()
        )
    ).scalar_one()

    # (22/1 + 46/2) / 2 = 22.5 bolsitas por kilo
    assert round(Decimal(rinde), 2) == Decimal("22.50")


def test_un_batch_con_default_aceptado_no_calibra_el_rinde(
    db_session, owner_user, cocinero_user, quinua, cocida
):
    """El anti-anclaje aplica a los DOS lados: aceptar el default de entrada sin
    pesar es tan falso como aceptar el de salida sin contar."""
    recipe, version = _make_recipe(db_session, owner_user, cocida, quinua)
    _make_batch(db_session, cocinero_user, recipe, version, quinua, measurement="default_input")
    _make_batch(db_session, cocinero_user, recipe, version, quinua, measurement="default_output")

    calibrantes = db_session.execute(
        sa.select(sa.func.count())
        .select_from(ManufacturingBatch)
        .where(ManufacturingBatch.recipe_id == recipe.id)
        .where(ManufacturingBatch.measurement == "measured")
    ).scalar_one()
    assert calibrantes == 0
