# Decisiones de backend — Orden de compra (Backend #1)

Respuestas a las 23 preguntas de backend para el modelo de datos de órdenes de compra (v0.3).
Cada respuesta indica qué se resuelve en el modelo (migración/tabla/constraint) y qué queda para
Backend #2 (endpoints), Backend #3 (tablero) o una decisión pendiente del dueño.

---

## P1 — Catálogo de proveedores

> ¿Los proveedores son texto libre o tienen catálogo?

**Cómo se resuelve en el modelo:** `purchase_orders.supplier_name TEXT NOT NULL`. Texto libre.
No hay tabla `suppliers` ni FK en este backend.

**Dónde se resuelve la parte no-modelo:** Deuda técnica documentada. La tabla `suppliers` con FK
va en un backend futuro. No entra en Backend #1 para mantener el PR chico.

---

## P2 — Dos órdenes abiertas mismo proveedor

> ¿Se permiten dos órdenes abiertas al mismo proveedor al mismo tiempo?

**Cómo se resuelve en el modelo:** Sí, permitido. No existe ningún `UNIQUE` constraint que lo
prohíba. Las órdenes se distinguen por `id` y `created_at`.

**Dónde se resuelve la parte no-modelo:** No aplica al shape de datos.

---

## P3 — Producto dos veces en la misma orden

> ¿Se puede cargar el mismo producto dos veces en una orden?

**Cómo se resuelve en el modelo:** NO. Garantizado por dos constraints complementarios:

1. El índice parcial único `uq_purchase_order_items_root_per_product` sobre
   `(purchase_order_id, product_id) WHERE corrects_id IS NULL` garantiza UNA RAÍZ
   por producto por orden (el primer ítem sin predecesor).
2. `UNIQUE(corrects_id)` global garantiza que la cadena de correcciones sea lineal
   (no bifurca — ningún ítem puede ser corregido dos veces simultáneamente).

Corolario: siempre hay UNA raíz y UNA hoja únicas por producto por orden, lo que
equivale a que no puede existir el mismo producto dos veces en estado "activo".

**Importante:** el índice apunta a la RAÍZ de la cadena, no a la hoja. La hoja
(ítem activo vigente) se identifica con:

```sql
NOT EXISTS (SELECT 1 FROM purchase_order_items x WHERE x.corrects_id = t.id)
```

No usar `corrects_id IS NULL` para encontrar el ítem vigente — eso devuelve la raíz.

**Dónde se resuelve la parte no-modelo:** No aplica al shape de datos.

---

## P4 — Exceso genera saldo negativo

> ¿Qué pasa si el operario registra más de lo pedido en la orden?

**Cómo se resuelve en el modelo:** Sí, permitido. `delivery_items.received_qty >= 0` permite
exceso. El saldo es derivado (Σ expected − Σ received por producto), no una columna persistida;
puede resultar negativo.

**Dónde se resuelve la parte no-modelo:** Backend #3 muestra la discrepancia al dueño en el
tablero.

---

## P5 — Reapertura recalcula saldo

> Al reabrir una orden cerrada, ¿el saldo vuelve a calcularse?

**Cómo se resuelve en el modelo:** El saldo es siempre derivado, no persistido. Reapertura = evento
`reopened` en `purchase_order_status_events`; no muta ítems. Si el dueño quiere pedir más
cantidad, corrige el ítem con un nuevo `purchase_order_items` con `corrects_id` y `expected_qty`
mayor.

**Dónde se resuelve la parte no-modelo:** El endpoint de edición de ítems va en Backend #2.

---

## P6 — Corrección de costo: PMP retroactivo o solo futuro

> Si se corrige el costo de un ítem, ¿el promedio ponderado se recalcula retroactivamente o solo rige hacia adelante?

**Cómo se resuelve en el modelo:** El modelo permite ambas semánticas. El PMP es un cálculo, no
un valor persistido. `purchase_order_item_costs` guarda la cadena de correcciones; la semántica
de cuál nodo usar para cada período la decide la query.

**Dónde se resuelve la parte no-modelo:** **Decisión abierta del dueño.** Backend #3 la
implementará. Recomendación técnica: retroactivo (coherente con append-only: el estado corregido
ES la verdad). Si el dueño prefiere que períodos pasados no cambien, se usa el costo vigente en
`created_at` de cada partida.

---

## P7 — Límite de correcciones de costo

> ¿Hay un límite de veces que se puede corregir un costo?

**Cómo se resuelve en el modelo:** NO. La cadena `corrects_id` es de longitud arbitraria.
`UniqueConstraint(corrects_id)` evita bifurcación, no limita la longitud de la cadena.

**Dónde se resuelve la parte no-modelo:** No aplica al shape de datos.

---

## P8 — Anulada se reabre o requiere orden nueva

> ¿Una orden anulada se puede reabrir?

**Cómo se resuelve en el modelo:** NO. El evento `reopened` solo aplica cuando el último evento
es `closed_auto` o `closed_manual`. El modelo permite insertar el registro técnicamente, pero la
invariante de negocio la enforce el endpoint.

El enum `purchase_order_status_event_type` distingue dos tipos de cierre:
- `closed_auto`: disparado por sistema cuando el operario valida la última partida que completa la
  orden. `created_by` puede ser operator o owner. Enforceado en DB: el trigger
  `trg_purchase_order_status_events_role_check` permite cualquier rol para `closed_auto`.
- `closed_manual`: dueño cierra la orden explícitamente. `created_by` debe ser owner. Enforceado
  en DB: el trigger rechaza `closed_manual` si `created_by` no tiene `role='owner'`.

La distinción vive en DB via enum + trigger BEFORE INSERT para garantizar que un operario no pueda
emitir un `closed_manual` disfrazado.

**Dónde se resuelve la parte no-modelo:** Backend #2 verifica el último evento y rechaza
`reopened` si el anterior fue `annulled`. El dueño crea una orden nueva en ese caso.

---

## P9 — Abandonar sin validar

> ¿Qué pasa si el operario empieza a registrar una partida pero no la valida?

**Cómo se resuelve en el modelo:** No hay tabla de "borrador". El estado no cambia hasta persistir.

**Dónde se resuelve la parte no-modelo:** Backend #2 solo persiste al POST de validación. El
flujo del operario en el frontend descarta lo no confirmado sin crear ningún registro.

---

## P10 — Item en 0

> ¿Se puede registrar un ítem con cantidad recibida = 0?

**Cómo se resuelve en el modelo:** Sí, permitido. `delivery_items.received_qty >= 0` (constraint
v0.2 sin cambios). El saldo pendiente de las otras partidas no se modifica.

**Dónde se resuelve la parte no-modelo:** No aplica al shape de datos.

---

## P11 — Exceso al saldo pendiente

> ¿El sistema permite registrar más de lo pendiente en la orden?

**Cómo se resuelve en el modelo:** Sí, permitido. Ver P4.

**Dónde se resuelve la parte no-modelo:** Backend #3 muestra la discrepancia al dueño.

---

## P12 — Producto no en la orden

> ¿El operario puede registrar un producto que no está en la orden?

**Cómo se resuelve en el modelo:** Comportamiento v0.2 se mantiene: no puede agregarse. Cuando
`deliveries.purchase_order_id IS NOT NULL` (partida de orden), la app-layer debe exigir que
`delivery_items.purchase_order_item_id IS NOT NULL` y que el ítem pertenezca a un ítem de la
orden.

**Dónde se resuelve la parte no-modelo:** Regla de app-layer en Backend #2. No hay constraint
de DB que lo enforece (hubiera requerido un trigger o FK compuesta con la orden, que complica
el esquema sin ganar mucho).

---

## P13 — Race condition offline

> Si dos operarios validan la misma partida simultáneamente, ¿cuál gana?

**Cómo se resuelve en el modelo:** Backend #2 usa primero-en-llegar-gana. El modelo no lleva
columna `version`. La `UNIQUE constraint` sobre `corrects_id` es la que gana races de corrección
concurrente: el segundo INSERT con el mismo `corrects_id` falla con `IntegrityError`.

**Dónde se resuelve la parte no-modelo:** Backend #2 captura el `IntegrityError` y devuelve
409 Conflict con mensaje claro.

---

## P14 — Ventana de corrección del operario

> ¿Durante cuánto tiempo puede el operario corregir una partida validada?

**Cómo se resuelve en el modelo:** No aplica al shape de datos.

**Dónde se resuelve la parte no-modelo:** Regla de negocio en Backend #2. Se valida `created_at`
con timezone Lima (`COCINA_BUSINESS_TIMEZONE`, default `America/Lima`).

---

## P15 — Umbral "por acabarse"

> ¿Cómo se determina que un producto está "por acabarse"?

**Cómo se resuelve en el modelo:** Ya existe `products.low_stock_threshold NUMERIC NULL CHECK > 0`.
Sin cambios en Backend #1.

**Dónde se resuelve la parte no-modelo:** Backend #3 calcula el stock actual y lo compara contra
el umbral.

---

## P16 — Desglose por plataforma

> ¿Se muestra el costo de consumo desglosado por plataforma (Rappi, PedidosYa…)?

**Cómo se resuelve en el modelo:** Ya existe `delivery_orders.platform TEXT NULL`. Sin cambios.

**Dónde se resuelve la parte no-modelo:** UX define si capturar y mostrar. Fuera de scope
de Backend #1.

---

## P17 — PMP histórico o por período

> ¿El promedio ponderado es acumulado histórico o por período?

**Cómo se resuelve en el modelo:** No aplica al shape de datos. PMP es siempre cálculo.

**Dónde se resuelve la parte no-modelo:** PMP histórico (acumulado desde la primera compra).
Backend #3.

---

## P18 — Costo de consumo del período

> ¿Cómo se calcula el costo de consumo del período?

**Cómo se resuelve en el modelo:** No aplica al shape de datos.

**Dónde se resuelve la parte no-modelo:** Cálculo: consumo por diferencia × PMP por producto.
Backend #3.

---

## P19 — Producto sin costo cargado

> ¿Qué pasa si un producto aparece en el tablero pero nunca tuvo costo cargado?

**Cómo se resuelve en el modelo:** El modelo lo permite. Una orden puede no incluir todos los
productos.

**Dónde se resuelve la parte no-modelo:** Backend #3 decide mostrar la cantidad sin costo con
etiqueta "sin costo cargado" en lugar de cero o vacío.

---

## P20 — Stock inicial del período

> ¿Qué se usa como stock inicial al calcular el consumo de un período?

**Cómo se resuelve en el modelo:** No aplica al shape de datos.

**Dónde se resuelve la parte no-modelo:** Backend #3 elige el `inventory_counts` completado más
reciente anterior al inicio del período.

---

## P21 — Ícono de advertencia en tablero

> ¿Cuándo aparece el ícono de advertencia en el tablero?

**Cómo se resuelve en el modelo:** No aplica al shape de datos.

**Dónde se resuelve la parte no-modelo:** Backend #3 dispara el ícono en casos matemáticamente
imposibles (p.ej., consumo mayor que stock inicial + entradas).

---

## P22 — Rol operario vs. dueño

> ¿Cómo se distingue quién puede ver costos y quién no?

**Cómo se resuelve en el modelo:** Ya existe `users.role ENUM('operator', 'owner')`. Backend #1
ya aplica el guard en DB via triggers `BEFORE INSERT`:

- `trg_purchase_orders_owner_creator`: exige `created_by` con `role='owner'` en `purchase_orders`.
- `trg_purchase_order_items_owner_creator`: idem en `purchase_order_items`.
- `trg_purchase_order_item_costs_owner_creator`: idem en `purchase_order_item_costs`.
- `trg_purchase_order_status_events_role_check`: exige `role='owner'` para `closed_manual`,
  `reopened` y `annulled`; permite cualquier rol válido para `closed_auto`.

**Dónde se resuelve la parte no-modelo:** Backend #2 debe seguir aplicando el guard en API-layer
como defensa en profundidad. Cualquier ruta que exponga costo al operario es un bug crítico
(criterio de aceptación de v0.3).

---

## P23 — CSV append-only

> ¿El export CSV muestra solo el estado actual o todas las correcciones?

**Cómo se resuelve en el modelo:** El modelo guarda todo append-only. Ambas semánticas de export
son implementables sobre los datos persistidos.

**Dónde se resuelve la parte no-modelo:** Decisión de auditoría pendiente del dueño. Backend #3.
