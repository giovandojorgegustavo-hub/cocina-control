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

## P6 — Corrección de costo: impacto en valuación FIFO por partidas

> Si se corrige el costo de un ítem, ¿cómo afecta la valuación (FIFO por partidas)?

**Cómo se resuelve en el modelo:** El modelo mantiene la cadena de correcciones de costo
(`purchase_order_item_costs` con `corrects_id`). Cada partida se valúa con el costo VIGENTE al
momento en que se registra la partida (join contra la hoja de la cadena de costos en ese
tiempo). Correcciones posteriores del costo NO retrocalculan partidas ya valuadas — cada
partida es un lote FIFO independiente con su propio costo capturado.

**Dónde se resuelve la parte no-modelo:** Backend #3 y la consulta de valuación FIFO
(agotamiento de partidas más viejas primero, requerimientos.md líneas 68-76).

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
- `closed_auto`: disparado por sistema cuando el cocinero valida la última partida que completa la
  orden. `created_by` puede ser cualquier rol. Enforceado en DB: el trigger
  `trg_purchase_order_status_events_role_check` permite cualquier rol para `closed_auto`.
- `closed_manual`: cierre explícito. `created_by` debe tener `role IN ('owner', 'admin')`.
  Enforceado en DB: el trigger rechaza `closed_manual` si `created_by` no tiene role en
  `('owner', 'admin')`.

Lo mismo aplica a `reopened` y `annulled`: solo aceptan `role IN ('owner', 'admin')` como `created_by`.

La distinción vive en DB via enum + trigger BEFORE INSERT para garantizar que un cocinero no pueda
emitir un `closed_manual` disfrazado.

**Dónde se resuelve la parte no-modelo:** Backend #2 verifica el último evento y rechaza
`reopened` si el anterior fue `annulled`. El dueño o admin crea una orden nueva en ese caso.

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

## P17 — Valuación de inventario: histórica o por período

> ¿La valuación del inventario es histórica o por período?

**Cómo se resuelve en el modelo:** Se calcula por FIFO sobre partidas remanentes. El inventario
valuado es Σ(remanente de partida × costo de esa partida) para todas las partidas con saldo > 0
del producto. Es siempre "estado actual" — no hay concepto de período para el cálculo del stock
valuado.

**Dónde se resuelve la parte no-modelo:** Backend #3 hace la query FIFO. El "costo de consumo del
período" es distinto — usa los eventos de consumo del rango.

---

## P18 — Costo de consumo del período

> ¿Cómo se calcula el costo de consumo del período?

**Cómo se resuelve en el modelo:** Suma del costo de todas las partidas AGOTADAS en el período
(por consumo, ajuste de salida FIFO, o combinación). Cada agotamiento apunta a la partida
específica (trazabilidad de qué tanda se consumió, requerimientos.md línea 71).

**Dónde se resuelve la parte no-modelo:** Backend #3. Los ajustes de conteo (entrada por
sobrante, salida FIFO por faltante) son eventos append-only definidos en requerimientos v0.5;
la tabla concreta y sus endpoints quedan para un slice posterior (fuera de Backend #2).

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

## P22 — Roles: cocinero, admin, dueño

> ¿Cómo se distingue quién puede ver costos y quién no?

**Cómo se resuelve en el modelo:** Ya existe `users.role ENUM('cocinero', 'owner', 'admin')`.

- **Cocinero**: rol de captura. Nunca ve plata; nunca puede insertar en `purchase_orders`,
  `purchase_order_items`, `purchase_order_item_costs` (rechazado por trigger); puede insertar
  eventos `closed_auto` (al validar partida que completa la orden).
- **Admin**: rol administrativo sin tablero. Puede crear órdenes con costos; puede insertar
  eventos `closed_manual`, `reopened`, `annulled` (trigger acepta owner O admin).
- **Owner**: dueño. Mismos permisos que admin + acceso al tablero (regla enforceada en
  Backend #3, no en este modelo).

Backend #1 ya aplica el guard en DB via triggers `BEFORE INSERT`:

- `trg_purchase_orders_admin_or_owner_creator`: exige `created_by` con `role IN ('owner', 'admin')` en `purchase_orders`.
- `trg_purchase_order_items_admin_or_owner_creator`: idem en `purchase_order_items`.
- `trg_purchase_order_item_costs_admin_or_owner_creator`: idem en `purchase_order_item_costs`.
- `trg_purchase_order_status_events_role_check`: exige `role IN ('owner', 'admin')` para
  `closed_manual`, `reopened` y `annulled`; permite cualquier rol para `closed_auto`.

**La regla de oro** (requerimientos.md líneas 197-201, 212-216) dice que las pantallas de
captura (verificar partida, contar, empacar) NO muestran plata para NINGÚN rol — ni siquiera
el dueño. Backend #2 debe garantizar que ningún response de endpoints de captura incluya
`unit_cost`, PMP, ni ningún dato monetario, independientemente del rol autenticado.

**Dónde se resuelve la parte no-modelo:** Backend #2 debe seguir aplicando el guard en API-layer
como defensa en profundidad. Cualquier ruta que exponga costo al cocinero es un bug crítico
(criterio de aceptación).

### Alcance de admin en flujos legacy (v0.2)

Admin comparte permisos operativos con el cocinero en los flujos v0.2
(deliveries, delivery_orders, inventory): puede recibir entregas, contar
inventario, completar pedidos, y corregir esos mismos artefactos dentro
de la ventana de corrección. Queda sujeto a las mismas ownership checks
que el cocinero (solo sus propios conteos/entregas en progreso).

Admin NO tiene acceso al tablero (owner-only). Admin NO ve la vista
extendida de items de inventario (corrects_id, reason) — esos siguen
siendo owner-only para preservar el conteo ciego en captura.

---

## P23 — CSV append-only

> ¿El export CSV muestra solo el estado actual o todas las correcciones?

**Cómo se resuelve en el modelo:** El modelo guarda todo append-only. Ambas semánticas de export
son implementables sobre los datos persistidos.

**Dónde se resuelve la parte no-modelo:** Decisión de auditoría pendiente del dueño. Backend #3.
