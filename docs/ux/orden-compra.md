# Orden de compra (v0.3 — flujo del dueño)

## Objetivo del flujo

Que el dueño pre-cargue una compra (proveedor, productos, cantidades y costos) antes de que el proveedor llegue. La orden queda abierta; cuando llegan las partidas, el operario las verifica usando el flujo de entrada (ver `registro-entrada.md`). El dueño puede seguir el estado de sus órdenes, ver lo que efectivamente llegó, reabrir una cerrada si hace falta, anular con motivo, y **editar la compra** (cantidad esperada y/o costo unitario de una línea) sin sobrescribir el registro original.

> **Revisión 13 jul 2026 — "no es corregir un costo, es editar la compra".** El flujo que antes se llamaba "corregir costo" se reencuadra: lo que el dueño edita es la **línea de la orden** — la cantidad esperada, el costo unitario, o ambos. Cada edición es un registro nuevo append-only que apunta al anterior (el modelo de backend ya soporta ambas cadenas). Ver Pantalla 6.

## Usuario

Dueño de la cocina. Escribe desde la computadora o la tablet, con la factura en la mano. Tiene tiempo para tipear; la meta aquí no es velocidad de captura sino exactitud (costos con 2 decimales) y visibilidad del estado de sus compras.

## Presupuesto

No aplica el techo de 5s/3 toques — es flujo del dueño, no del operario. La meta es:

- **Orden nueva:** menos de 90 segundos desde "nueva orden" hasta guardar.
- **Vista del estado de las órdenes:** legible en menos de 3 segundos.

## Punto de entrada en el tablero (Pantalla 0)

El dueño accede desde el tablero. El widget "Órdenes de compra abiertas" incluye el acceso directo.

```
+------------------------------------------------------------------------------+
|  Cocina Control — Tablero                             Dueño  |  cerrar sesión |
+------------------------------------------------------------------------------+
|  ...  (barra de período, widgets de por acabarse, pedidos, costos)          |
|                                                                              |
|  +------------------------------------------+                               |
|  |  ORDENES DE COMPRA ABIERTAS              |                               |
|  |                                          |                               |
|  |  Abiertas          3                     |                               |
|  |  Recibidas parcial 1                     |                               |
|  |  Total pendiente   S/. 1.240,00          |                               |
|  |                                          |                               |
|  |  [ ver todas las órdenes ]  [ + nueva ]  |                               |
|  +------------------------------------------+                               |
+------------------------------------------------------------------------------+
```

- **"+ nueva"** abre directamente la pantalla de armar orden (Pantalla 1).
- **"ver todas las órdenes"** abre la lista completa (Pantalla 2).

---

## Pantalla 1 — Armar una orden nueva

Formulario limpio. El dueño elige proveedor, luego agrega productos uno a uno con cantidad y costo unitario. El total se calcula en tiempo real.

```
+------------------------------------------------------------------------------+
|  <  NUEVA ORDEN DE COMPRA                                                    |
+------------------------------------------------------------------------------+
|                                                                              |
|  Proveedor                                                                   |
|  +----------------------------------------------------------------------+   |
|  |  Verduleria Nuñez                                           ▼        |   |
|  +----------------------------------------------------------------------+   |
|                                                                              |
|  Productos en esta orden                                                     |
|  +----------------------------------------------------------------------+   |
|  |  Producto          |  Cant.  |  Unidad  |  Costo unit.  |  Total    |   |
|  |--------------------|---------|----------|---------------|-----------|   |
|  |  PALTA             |    30   |   un.    |   S/. 1,20    | S/. 36,00 |   |
|  |  TOMATE            |    15   |   kg     |   S/. 3,50    | S/. 52,50 |   |
|  |  CEBOLLA           |    10   |   kg     |   S/. 2,00    | S/. 20,00 |   |
|  +----------------------------------------------------------------------+   |
|                                                                              |
|  [ + agregar producto ]                                                      |
|                                                                              |
|  -----------------------------------------------------------------------     |
|  Total de la orden                                          S/. 108,50       |
|  -----------------------------------------------------------------------     |
|                                                                              |
|  [ cancelar ]                              [ guardar orden — abierta  ]      |
+------------------------------------------------------------------------------+
```

### Fila de producto (al agregar o editar)

Cada fila se puede editar inline. Al tocar "agregar producto", aparece una fila nueva con foco en el selector de producto:

```
|  +----------------------------------------------------------------------+   |
|  |  [ elegir producto... ▼ ]  |  [ 0 ] |  [ un. ] |  [ S/. 0,00 ] |  —  |   |
|  +----------------------------------------------------------------------+   |
```

- El selector de producto muestra la lista del catálogo activo. No permite texto libre.
- La unidad se completa automáticamente desde el catálogo — no editable.
- El costo unitario acepta hasta 2 decimales. El total de fila = cant. × costo unit., se calcula al salir del campo.
- El ícono "—" a la derecha borra la fila (solo antes de guardar).
- Guardar con una fila vacía no está permitido; el botón "guardar orden" queda deshabilitado si algún campo requerido falta.

### Qué guarda "guardar orden"

- Proveedor, fecha-hora de creación (UTC, mostrada en hora Lima), quién la creó.
- Por ítem: producto, cantidad esperada, costo unitario. Total calculado como referencia.
- Estado inicial: **abierta**.

> PREGUNTA A BACKEND: ¿el catálogo de proveedores es una lista fija o el dueño puede escribir uno libre? Asumo: lista cerrada administrada por el dueño. Si no existe la opción, no aparece en el selector.

> PREGUNTA A BACKEND: ¿puede haber dos órdenes abiertas del mismo proveedor simultáneamente? Asumo: sí — no hay restricción. El dueño las distingue por fecha y por los productos incluidos.

> PREGUNTA A BACKEND: ¿puede el mismo producto aparecer dos veces en la misma orden? Asumo: no — el sistema lo previene en el selector (ya aparece en gris/deshabilitado si está en la orden).

---

## Pantalla 2 — Lista de órdenes

Vista completa de todas las órdenes, con filtros por estado. Las abiertas y recibidas parcialmente van arriba; el resto es historial.

```
+------------------------------------------------------------------------------+
|  <  ORDENES DE COMPRA                                        [ + nueva ]     |
+------------------------------------------------------------------------------+
|  [ Abiertas ] [ Recibida parcial ] [ Cerradas ] [ Anuladas ] [ Todas ]       |
+------------------------------------------------------------------------------+
|                                                                              |
|  +------------------------------------------------------------------------+  |
|  |  VERDULERIA NUÑEZ           [ ABIERTA ]          12 jul 2026 — 09:14   |  |
|  |  3 productos · S/. 108,50                                              |  |
|  +------------------------------------------------------------------------+  |
|                                                                              |
|  +------------------------------------------------------------------------+  |
|  |  CARNICERIA LOPEZ           [ RECIBIDA PARCIAL ]  10 jul 2026 — 16:30  |  |
|  |  1 producto con saldo · faltan 40 kg de POLLO · S/. 280,00 pendiente   |  |
|  +------------------------------------------------------------------------+  |
|                                                                              |
|  +------------------------------------------------------------------------+  |
|  |  DISTRIBUIDORA SUR (gris)   [ CERRADA ✓ ]         8 jul 2026 — 11:00  |  |
|  |  5 productos · S/. 342,00 recibido                                     |  |
|  +------------------------------------------------------------------------+  |
|                                                                              |
|  +------------------------------------------------------------------------+  |
|  |  CARNICERIA LOPEZ (gris)    [ ANULADA ]            5 jul 2026 — 14:22  |  |
|  |  Anulada el 6 jul · 2 partidas recibidas conservadas                   |  |
|  +------------------------------------------------------------------------+  |
+------------------------------------------------------------------------------+
```

### Reglas de layout por estado

| Estado              | Color de fila  | Badge           | Qué muestra en el resumen                                      |
|---------------------|----------------|-----------------|----------------------------------------------------------------|
| Abierta             | Fondo claro    | Oscuro "ABIERTA" | N productos, total de la orden en soles                       |
| Recibida parcial    | Fondo amarillo | Amarillo "RECIBIDA PARCIAL" | Qué falta y cuánto falta en plata                |
| Cerrada             | Gris           | Gris "CERRADA ✓" | Total efectivamente recibido en soles                         |
| Anulada             | Gris           | Gris "ANULADA"  | Fecha de anulación, cuántas partidas quedaron registradas      |

Tocar una fila abre el detalle de la orden (Pantalla 3).

---

## Pantalla 3 — Detalle de una orden

Vista completa: lo que se pidió, cada partida que llegó (con quién y cuándo la registró), y el saldo pendiente por producto.

```
+------------------------------------------------------------------------------+
|  <  ORDEN — Carniceria Lopez                 [ RECIBIDA PARCIAL ]            |
|  Creada el 10 jul 2026 — 16:30 (Juan Dueño)                                 |
+------------------------------------------------------------------------------+
|                                                                              |
|  PRODUCTOS DE LA ORDEN                                                       |
|  +------------------------------------------------------------------------+  |
|  | Producto  | Pedido  | Recibido | Saldo    | Costo unit. | Total recib. |  |
|  |-----------|---------|----------|----------|-------------|--------------|  |
|  | POLLO     |  100 kg |   60 kg  |  40 kg ← |   S/. 7,00  |  S/. 420,00  |  |
|  | CERDO     |   20 kg |   20 kg  |    —  ✓  |   S/. 9,50  |  S/. 190,00  |  |
|  +------------------------------------------------------------------------+  |
|                                                                              |
|  Total pedido:    S/. 890,00                                                  |
|  Total recibido:  S/. 610,00                                                  |
|  Saldo pendiente: S/. 280,00                                                  |
|                                                                              |
|  PARTIDAS RECIBIDAS                                                           |
|  +------------------------------------------------------------------------+  |
|  | Partida | Fecha         | Registró  | Productos (cantidades recibidas) |  |
|  |---------|---------------|-----------|----------------------------------|  |
|  | #2      | 12 jul · 09:30 | María Op. | POLLO 30 kg, CERDO 20 kg        |  |
|  | #1      | 11 jul · 14:05 | Juan Op.  | POLLO 30 kg                     |  |
|  +------------------------------------------------------------------------+  |
|                                                                              |
|  [ anular orden ]                            [ reabrir ]  (solo si cerrada) |
+------------------------------------------------------------------------------+
```

- El saldo pendiente por producto: cantidad pedida menos la suma de todas las partidas recibidas para ese producto.
- "✓" en la columna "Saldo" indica que ese producto está completo.
- "← " en la columna "Saldo" indica que todavía falta.
- Si la orden tiene ediciones (cantidad esperada y/o costo de alguna línea), se muestra "ver historial de la orden", que abre el historial de la **orden completa** (ver Pantalla 6). La edición en sí es por línea: cada línea permite abrir el modal "editar compra".
- Los totales en soles aparecen porque es vista del dueño.
- El botón "reabrir" solo es visible si la orden está en estado **cerrada**. Si está abierta o recibida parcial, no aparece.
- El botón "anular orden" siempre visible mientras la orden no esté ya anulada.

> PREGUNTA A BACKEND: cuando el operario registra una partida con exceso (más de lo pedido), ¿el saldo puede quedar en negativo? Asumo: sí; el sistema acepta el exceso y lo muestra en la columna "Saldo" como "−10 kg (exceso)". La fila se marca con una advertencia visual, pero no bloquea nada.

---

## Pantalla 4 — Reabrir una orden cerrada

El dueño toca "reabrir" en una orden cerrada. Aparece un modal de confirmación con campo de motivo libre.

```
+------------------------------------------------------------------------------+
|                                                                              |
|  +-----------------------------------------+                                |
|  |  REABRIR ORDEN                          |                                |
|  |  Carniceria Lopez — cerrada el 12 jul   |                                |
|  |                                         |                                |
|  |  Motivo (campo libre)                   |                                |
|  |  +-----------------------------------+  |                                |
|  |  |  El proveedor mandó 10 kg más     |  |                                |
|  |  |  de pollo el 14 jul               |  |                                |
|  |  +-----------------------------------+  |                                |
|  |                                         |                                |
|  |  [ cancelar ]       [ reabrir orden ]   |                                |
|  +-----------------------------------------+                                |
|                                                                              |
+------------------------------------------------------------------------------+
```

Al confirmar:

- Se crea un **evento de reapertura** (append-only): quién, cuándo, motivo.
- La orden vuelve a estado **abierta**.
- En el detalle de la orden, aparece una línea en el historial: "Reabierta el 14 jul 2026 — 11:05 (Juan Dueño) — Motivo: El proveedor mandó 10 kg más de pollo el 14 jul".
- El operario la vuelve a ver en su bandeja como abierta, con el saldo pendiente calculado a partir de todo lo ya recibido.

> PREGUNTA A BACKEND: ¿la reapertura recalcula automáticamente el saldo pendiente a partir de las partidas ya registradas? Asumo: sí — el saldo se recalcula contra la cantidad esperada **vigente** de cada línea. Si el dueño quiere pedir más cantidad de un producto, edita la compra (Pantalla 6): la cantidad esperada vigente sube y el saldo pendiente se recalcula solo.

---

## Pantalla 5 — Anular una orden

El dueño toca "anular orden". Si hay partidas recibidas, el sistema muestra una advertencia clara antes de confirmar.

### Caso A: sin partidas recibidas

```
+------------------------------------------------------------------------------+
|                                                                              |
|  +-----------------------------------------+                                |
|  |  ANULAR ORDEN                           |                                |
|  |  Verduleria Nuñez — abierta             |                                |
|  |                                         |                                |
|  |  No llegó nada de esta orden.           |                                |
|  |                                         |                                |
|  |  Motivo (campo libre)                   |                                |
|  |  +-----------------------------------+  |                                |
|  |  |  El proveedor canceló la entrega  |  |                                |
|  |  +-----------------------------------+  |                                |
|  |                                         |                                |
|  |  [ cancelar ]       [ anular orden ]    |                                |
|  +-----------------------------------------+                                |
|                                                                              |
+------------------------------------------------------------------------------+
```

### Caso B: con partidas ya recibidas

```
+------------------------------------------------------------------------------+
|                                                                              |
|  +-----------------------------------------+                                |
|  |  ANULAR ORDEN                           |                                |
|  |  Carniceria Lopez — recibida parcial    |                                |
|  |                                         |                                |
|  |  ⚠ Esta orden tiene 2 partidas           |                                |
|  |  recibidas (60 kg de POLLO + 20 kg      |                                |
|  |  de CERDO). Esas partidas impactaron     |                                |
|  |  el stock y quedan registradas.          |                                |
|  |  La anulación no revierte el stock.     |                                |
|  |                                         |                                |
|  |  Motivo (campo libre)                   |                                |
|  |  +-----------------------------------+  |                                |
|  |  |                                   |  |                                |
|  |  +-----------------------------------+  |                                |
|  |                                         |                                |
|  |  [ cancelar ]       [ anular igual ]    |                                |
|  +-----------------------------------------+                                |
|                                                                              |
+------------------------------------------------------------------------------+
```

Al confirmar en cualquier caso:

- Se crea un **evento de anulación** (append-only): quién, cuándo, motivo.
- La orden pasa a estado **anulada**.
- Las partidas recibidas antes quedan intactas en el historial y en el stock.
- En la lista de órdenes, la fila aparece gris con badge "ANULADA" y el texto "N partidas recibidas conservadas".

---

## Pantalla 6 — Historial de la orden

Accesible desde el detalle de la orden (Pantalla 3), al tocar "ver historial de la orden". Muestra las **ediciones de la compra** de la orden completa: cantidad esperada y costo unitario, no solo costo.

**Regla: se edita por línea, se audita por orden.** El modal de edición opera sobre UNA línea (un producto); este historial muestra TODAS las ediciones de TODAS las líneas de la orden, mezcladas y ordenadas por fecha descendente, con columna Producto para distinguirlas.

**Este historial es DE LA ORDEN** — el lado "entrada de plata": qué se pidió y a qué precio, con sus ediciones append-only. No es un historial del producto (los movimientos del producto — partidas, pedidos, conteos — viven en la trazabilidad del tablero).

Pueden editar la compra el **dueño y el admin** (revisión de roles del 13 jul 2026); el cocinero no accede a esta pantalla.

```
+------------------------------------------------------------------------------+
|  <  HISTORIAL DE LA ORDEN — Carniceria Lopez                                 |
+------------------------------------------------------------------------------+
|                                                                              |
|  +------------------------------------------------------------------------+  |
|  | Fecha          Producto  Cant. esp.  Costo unit.  Registró    Nota    |  |
|  |----------------|---------|-----------|------------|------------|--------|  |
|  | 12 jul · 10:15  POLLO      110 kg     S/. 7,50    Juan Dueño  edita   |  |
|  |                                                                compra  |  |
|  | 10 jul · 16:30  CERDO       20 kg     S/. 9,50    Juan Dueño  [orig.] |  |
|  | 10 jul · 16:30  POLLO      100 kg     S/. 7,00    Juan Dueño  [orig.] |  |
|  +------------------------------------------------------------------------+  |
|                                                                              |
|  Vigente: POLLO 110 kg @ S/. 7,50 · CERDO 20 kg @ S/. 9,50                   |
|                                                                              |
|  [ + editar compra ]                                                         |
+------------------------------------------------------------------------------+
```

- Cada fila es un registro append-only de una línea: el original ([registro original]) o una edición que apunta al anterior de la misma línea.
- **"+ editar compra"** abre el modal para la línea que el dueño elija. También se llega directo desde la línea en el detalle de la orden (Pantalla 3).

Al tocar "editar compra":

```
+------------------------------------------------------------------------------+
|                                                                              |
|  +------------------------------------------+                               |
|  |  EDITAR COMPRA — POLLO                   |                               |
|  |  Vigente: 100 kg · S/. 7,00 / kg         |                               |
|  |                                          |                               |
|  |  Cantidad esperada                       |                               |
|  |  +-------------------------------+       |                               |
|  |  |  [ 100 ]  kg                  |       |                               |
|  |  +-------------------------------+       |                               |
|  |                                          |                               |
|  |  Costo unitario                          |                               |
|  |  +-------------------------------+       |                               |
|  |  |  S/.  [ 7,00 ]                |       |                               |
|  |  +-------------------------------+       |                               |
|  |                                          |                               |
|  |  Motivo (opcional)                       |                               |
|  |  +-------------------------------+       |                               |
|  |  |  Factura llegó con precio     |       |                               |
|  |  |  ajustado                     |       |                               |
|  |  +-------------------------------+       |                               |
|  |                                          |                               |
|  |  [ cancelar ]      [ guardar edición ]   |                               |
|  +------------------------------------------+                               |
|                                                                              |
+------------------------------------------------------------------------------+
```

- Los dos campos vienen **precargados con los valores vigentes**. El dueño cambia uno, el otro, o ambos.
- Guardar sin cambiar nada no crea registro (el botón queda deshabilitado si ambos valores son iguales a los vigentes).

Al guardar:

- Se crea un **registro nuevo de edición** que apunta al registro anterior (append-only). El original nunca se toca. El modelo de backend ya soporta ambas cadenas: cantidad esperada y costo.
- Los valores vigentes de la línea pasan a ser los nuevos.
- El saldo pendiente de la línea se recalcula contra la cantidad esperada vigente.
- El historial muestra todos los registros, ordenados más reciente primero.
- El tablero del dueño y la valuación FIFO usan el costo vigente de la línea para las partidas de esta orden.

> **Nota — esto NO reemplaza la corrección de cantidades RECIBIDAS.** Editar la compra toca lo que se **pidió** (cantidad esperada) y a qué **precio**. Lo que efectivamente **llegó** lo registra el operario al verificar cada partida — flujo de v0.2, sin cambios (ver `registro-entrada.md`). Compra y entrada siguen siendo hechos distintos con registros distintos.

> PREGUNTA A BACKEND: ¿la edición del costo afecta retroactivamente la valuación FIFO de agotamientos ya minados? Asumo: la valuación es minería posterior recomputable desde los eventos; el costo vigente de la línea rige para las partidas de esta orden. Confirmar si los cálculos ya publicados de períodos anteriores se recomputan o se corrigen hacia adelante.

> PREGUNTA A BACKEND: ¿hay un límite de ediciones por línea? Asumo: no hay límite. Cada edición es un registro más en el historial.

---

## Estados del flujo completo

### Vacío (no hay órdenes)

```
+------------------------------------------------------------------------------+
|  <  ORDENES DE COMPRA                                        [ + nueva ]     |
+------------------------------------------------------------------------------+
|                                                                              |
|         No hay órdenes de compra todavía.                                   |
|         Creá la primera desde "+ nueva".                                     |
|                                                                              |
+------------------------------------------------------------------------------+
```

### Cargando

Skeletons con la forma de las filas de la lista. Nunca spinner solo.

### Error (al guardar una orden nueva)

Toast rojo no bloqueante. El formulario conserva todos los datos tipeados:

```
+-------------------------------------------------------------------+
|  No se pudo guardar la orden. Los datos no se perdieron — tocá de  |
|  nuevo para reintentar.                                            |
+-------------------------------------------------------------------+
```

### Sin conexión

Banner naranja arriba, no bloquea la lectura de las órdenes ya cargadas. Si el dueño guarda una orden offline, se encola y se sincroniza al volver la red:

```
+------------------------------------------------------------------------------+
|  Sin conexión — los cambios se guardan cuando vuelva la red                  |
+------------------------------------------------------------------------------+
```

---

## Correcciones en este flujo

- **Estructura de la orden (proveedor, alta/baja de líneas):** editable mientras no haya partidas registradas; congelada a partir de la primera partida. Ver pregunta a backend sobre edición de entregas anunciadas en `registro-entrada.md`.
- **Cantidad esperada y costo unitario de una línea:** siempre editables con registro nuevo — "editar compra", ver Pantalla 6. No hay ventana de tiempo — dueño y admin pueden editar en cualquier momento, incluso con partidas recibidas.
- **Cantidades recibidas:** NO se corrigen acá — la corrección de una partida es el flujo del operario de v0.2 (`registro-entrada.md`).
- **Anulación:** no es reversible excepto por reapertura explícita. Pero al ser todo append-only, el registro de anulación siempre está. Un order anulada NO se puede reabrir — crear una nueva orden si hace falta.

> PREGUNTA A BACKEND: ¿una orden anulada puede reabrirse o solo crear una nueva? Decisión de diseño asumida: no se reabre — se crea una nueva. Confirmar con el dueño.

---

## Qué SÍ se muestra en este flujo (diferencia con el operario)

- Costos unitarios por producto.
- Total de la orden, total recibido, saldo pendiente en soles.
- Quién registró cada partida y cuándo.
- Historial de ediciones de la orden (cantidad esperada y costo), con registros anteriores visibles.

## Qué NO se muestra en este flujo

- Valuación FIFO ni remanentes por partida (eso es cálculo del tablero — ver "Partidas por producto" en `tablero-dueno.md`).
- Stock actual del producto al momento de crear la orden (no es análisis del dueño en este contexto).
- Datos de pedidos o inventarios asociados (ese cruce es el tablero, no la orden).
