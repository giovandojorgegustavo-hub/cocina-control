# Tablero del dueño (v0.3 — con costos y órdenes de compra)

> **Qué cambió respecto de v0.2:**
> - Se suman tres widgets nuevos: **Costo de inventario**, **Costo de consumo del período** y **Órdenes de compra abiertas**.
> - La tabla de consumo y stock gana una columna **Costo consumo** (valuado por FIFO por partidas).
> - La vista de trazabilidad por producto suma los eventos de tipo **PARTIDA** y **ORDEN** (además de los ya existentes).
> - Nueva sección al final: cómo el dueño arranca una orden nueva desde el tablero.
>
> **Revisión 13 jul 2026 — FIFO por partidas:** la decisión de valuación cambió de promedio ponderado (PR #95) a **FIFO por partidas**. Ya no existe un "costo vigente" único por producto: el valor del stock es la **suma de las partidas remanentes, cada una a su costo**. Este documento se actualizó: toda mención a PMP fue reemplazada, y se agregó la pantalla **"Partidas por producto"**.

---

## Objetivo del flujo

Que el dueño, de un solo vistazo, vea el estado del inventario: consumo por diferencia del último período, stock actual, productos por acabarse, **cuánta plata hay parada en depósito**, **cuánta plata se consumió en el período** y **qué órdenes de compra están pendientes de recibir**. Cero acciones necesarias — solo lectura. Salvo el botón de nueva orden, que está disponible desde el widget correspondiente.

Alineado con el principio rector: la captura optimiza fidelidad; este tablero es la minería posterior sobre esos datos crudos. Los costos que se muestran acá los cargó el dueño al crear las órdenes de compra.

## Usuario

Dueño de la cocina. Mira desde el escritorio, en pausa entre tareas. Prioriza velocidad de lectura sobre densidad de datos. Puede entrar a detalle si algo le llama la atención.

## Presupuesto

No aplica el techo de 3 toques / 5 segundos — no es un flujo de captura. La meta:

- **Vista principal legible en menos de 3 segundos.**
- **Producto por acabarse identificable de un vistazo (visual, no textual).**
- **Costo de inventario y costo de consumo legibles sin calcular nada.**

## Acceso

- Solo el dueño ve este tablero. Login separado del operario o rol distinto en el mismo login.
- El operario nunca ve este tablero. Ni siquiera un link o preview.
- Desde acá el dueño también **arranca órdenes de compra** (ver sección al final y `orden-compra.md`) y **pide conteos de inventario** (ver `registro-inventario.md`).

> PREGUNTA A BACKEND: ¿existe el concepto de rol (operario vs dueño) en el modelo de usuarios, o hay una app distinta por rol? Asumo: mismo login, distinto rol. El rol "operario" nunca puede acceder a la ruta del tablero ni a ninguna ruta que exponga costos.

---

## Nota sobre FIFO por partidas

El método de valuación es **FIFO por partidas** (decisión resuelta en PR #95 como promedio ponderado, **revisada por el dueño el 13 jul 2026**). Es una convención contable: el consumo agota partidas *en papel*, la más vieja primero, sin pretender saber qué kilo físico salió de qué tanda.

- **Costo de consumo** = suma de lo agotado de cada partida, de la más vieja a la más nueva, cada tramo a su costo.
- **Costo de inventario** = suma de las **partidas remanentes**, cada una a su costo unitario. No hay un costo único por producto — hay tantos costos como partidas remanentes.

Ejemplo: llegaron 30 kg de pollo a S/. 7,00 y después 40 kg a S/. 8,00. Se consumieron 35 kg → agotan los 30 kg de la primera partida (S/. 210,00) más 5 kg de la segunda (S/. 40,00) = **S/. 250,00 de consumo**. Quedan 35 kg remanentes de la segunda partida a S/. 8,00 = **S/. 280,00 de inventario**.

La valuación es minería posterior: partidas remanentes y agotamientos se derivan de los eventos y son recomputables desde cero. Esta nota aparece una vez en este documento, como referencia. No se muestra en pantalla al dueño — se asume que lo entiende o que el onboarding se lo explica.

---

## Vista principal

Pensada para pantalla grande (desktop 1440+) o tablet horizontal. En celular vertical se apila y los widgets de alerta quedan arriba de todo.

Desktop / tablet horizontal:

```
+------------------------------------------------------------------------------+
|  Cocina Control — Tablero                             Dueño  |  cerrar sesión |
+------------------------------------------------------------------------------+
|                                                                              |
|  [ HOY ] [ 7 días ] [ 30 días ] [ personalizado ]  último inventario: ayer 23:15 |
|                                                                              |
|  +-------------------------------+  +-----------------------------------+    |
|  |  POR ACABARSE                 |  |  PEDIDOS EN EL PERÍODO            |    |
|  |                               |  |                                   |    |
|  |  PALTA         ●●○ 4 un.      |  |  Terminados (con detalle)   38   |    |
|  |  QUESO         ●○○ 0,5 kg     |  |  Solo foto                   5   |    |
|  |  LIMON         ●○○ 2 un.      |  |  -----------------------------   |    |
|  |                               |  |  Total                      43   |    |
|  |  [ ver todos ]                |  |                                   |    |
|  +-------------------------------+  +-----------------------------------+    |
|                                                                              |
|  +-------------------------------+  +-----------------------------------+    |
|  |  COSTO DE INVENTARIO          |  |  COSTO DE CONSUMO DEL PERÍODO    |    |
|  |                               |  |                                   |    |
|  |  S/. 2.340,80                 |  |  S/. 1.120,50                    |    |
|  |  plata parada en depósito     |  |  valuado por FIFO · 7 días       |    |
|  |  suma de remanentes (FIFO)    |  |                                   |    |
|  |                               |  |  [ ver detalle por producto ]    |    |
|  |  [ ver partidas x producto ]  |  |                                   |    |
|  +-------------------------------+  +-----------------------------------+    |
|                                                                              |
|  +------------------------------------------+                               |
|  |  ORDENES DE COMPRA ABIERTAS              |                               |
|  |                                          |                               |
|  |  Abiertas            3                   |                               |
|  |  Recibidas parcial   1                   |                               |
|  |  Total pendiente     S/. 1.240,00        |                               |
|  |                                          |                               |
|  |  [ ver todas las órdenes ]  [ + nueva ]  |                               |
|  +------------------------------------------+                               |
|                                                                              |
|  CONSUMO Y STOCK POR PRODUCTO                                                |
|  +------------------------------------------------------------------------+  |
|  | Producto  | Stock ahora | Entradas | Consumo (diff) | Costo consumo  | Alerta |  |
|  |-----------|-------------|----------|----------------|----------------|--------|  |
|  | PALTA     |     4 un    |   20 un  |    18 un       |  S/. 21,60     | ●● x acabar |  |
|  | POLLO     |    12 kg    |   70 kg  |    58 kg       |  S/. 438,86    |             |  |
|  | TOMATE    |     8 kg    |   15 kg  |    12 kg       |  S/. 42,00     |             |  |
|  | CEBOLLA   |     3 kg    |   10 kg  |     9 kg       |  S/. 18,00     |             |  |
|  | QUESO     |   0,5 kg    |    5 kg  |     6 kg ⚠     |  S/. 54,00     | ● x acabar  |  |
|  +------------------------------------------------------------------------+  |
|                                                                              |
|  [ descargar CSV ]                       [ ver trazabilidad por producto ]   |
+------------------------------------------------------------------------------+
```

### Widget "por acabarse" (arriba a la izquierda) — sin cambios de v0.2

- Lista corta, máximo 5 productos.
- Semáforo visual por producto: círculos llenos/vacíos ● ○ ○ indicando nivel relativo al umbral.
- El valor numérico (stock) al lado, secundario visualmente. Lo importante es el color.
- "Ver todos" abre la tabla completa filtrada por productos bajo umbral.

> PREGUNTA A BACKEND: ¿el umbral "por acabarse" es fijo por producto (definido por el dueño en el catálogo), calculado por consumo promedio, o híbrido? Asumo por ahora: fijo, cargado por el dueño en el catálogo. Si no está cargado, no aparece en "por acabarse" pero sí en la tabla.

### Widget "pedidos en el período" (arriba a la derecha) — sin cambios de v0.2

- Conteo de pedidos por estado: terminados y solo-foto. Total abajo.
- Un número alto de "solo foto" persistente es señal para el dueño de que el detalle no se está completando.
- No abre detalle en v0.3 — es solo lectura rápida.

> PREGUNTA A BACKEND (y al dueño): v0.2 no captura la plataforma (Rappi / PedidosYa) en el flujo del operario. ¿El dueño necesita el desglose por plataforma antes de que lleguen las integraciones por API?

### Widget "Costo de inventario" (nuevo en v0.3)

- **Un número grande:** total en soles de lo que hay en stock ahora = **suma de las partidas remanentes de todos los productos, cada una a su costo** (FIFO).
- Etiqueta secundaria: "plata parada en depósito · suma de remanentes (FIFO)".
- No depende del período seleccionado en la barra — siempre es "ahora".
- **"ver partidas por producto"** abre el detalle de partidas remanentes (ver la vista "Partidas por producto" más abajo), arrancando por la lista de productos con stock valuado.

> PREGUNTA A BACKEND: el costo de inventario se calcula como suma de (remanente de cada partida × costo unitario de esa partida), sobre todas las partidas históricas no agotadas. El período seleccionado no afecta este cálculo — ¿correcto? Asumo: sí; el período solo afecta la ventana de consumo.

### Widget "Costo de consumo del período" (nuevo en v0.3)

- **Un número grande:** total en soles del consumo del período seleccionado, valuado por FIFO.
- Etiqueta secundaria: "valuado por FIFO · [etiqueta del período seleccionado]".
- Cambia cuando el dueño cambia el período en la barra.
- "Ver detalle por producto" abre la tabla filtrada con el consumo y costo por producto para el período.

> PREGUNTA A BACKEND: el costo de consumo del período se calcula agotando partidas de la más vieja a la más nueva y sumando lo agotado de cada una a su costo. ¿Es correcto? Asumo: sí. El consumo por diferencia ya existe en v0.2; las partidas con costo vienen de las órdenes registradas en v0.3.

> PREGUNTA A BACKEND: ¿qué pasa si un producto tiene consumo registrado pero no tiene ningún costo cargado (sin órdenes de compra con ese producto)? Asumo: se muestra el consumo en cantidad pero la columna "Costo consumo" queda vacía con etiqueta "sin costo cargado" para ese producto. El total del widget excluye ese producto.

### Widget "Órdenes de compra abiertas" (nuevo en v0.3)

- Conteo de órdenes por estado activo: abiertas (sin ninguna partida) y recibidas parcialmente.
- Total pendiente en soles: suma de saldos pendientes de todas las órdenes abiertas y recibidas parcialmente.
- **"ver todas las órdenes"** abre el panel completo de órdenes (pantalla 2 de `orden-compra.md`).
- **"+ nueva"** abre el formulario de nueva orden (pantalla 1 de `orden-compra.md`).

### Tabla "consumo y stock por producto" (v0.3 — con columna nueva)

Una fila por producto activo del catálogo. Columnas:

- **Producto** — nombre en mayúsculas.
- **Stock ahora** — último inventario registrado, ajustado por partidas validadas posteriores.
- **Entradas** — suma de lo recibido en partidas **validadas** en el rango elegido (el valor recibido en la partida, no lo pedido en la orden).
- **Consumo (diff)** — cálculo: `stock inicial + entradas − stock actual`. Consumo por diferencia, igual que v0.2.
- **Costo consumo** *(nuevo)* — consumo por diferencia valuado por **FIFO por partidas**: el consumo agota partidas de la más vieja a la más nueva y se suma lo agotado de cada una a su costo. Si no hay costo cargado para el producto, celda vacía con "—".
- **Alerta** — semáforo visual.

Ordenada por defecto por "alerta" descendente, después por consumo descendente.

> PREGUNTA A BACKEND: la fórmula de consumo por diferencia necesita un "stock de inicio del período". ¿Se toma el último inventario anterior al inicio del rango, o el primero dentro del rango? Asumo: último inventario anterior. Si no existe, se muestra "sin dato de inicio" en esa fila.

> PREGUNTA A BACKEND: ¿qué dispara el ícono de advertencia "⚠" en la columna de consumo? En v0.2 y v0.3 asumo solo casos matemáticamente imposibles (consumo negativo, stock actual mayor que stock inicial + entradas). Alertas por desviación quedan para cuando haya recetas (v0.4).

---

## Vista de partidas por producto (nueva — revisión FIFO)

El detalle de la valuación: qué partidas remanentes componen el stock de un producto y cuánto vale cada una. Es la pantalla que hace tangible el FIFO — "quedan 2 kg de la tanda del martes".

**Acceso** (todas rutas del tablero → **solo dueño**, igual que todo el tablero):

- Desde el widget "Costo de inventario" → "ver partidas por producto" (lista de productos con stock valuado; tocar uno abre esta vista).
- Desde la tabla "consumo y stock por producto" → tocar el valor de la columna "Stock ahora".
- Desde la trazabilidad del producto → link "ver partidas remanentes".

```
+------------------------------------------------------------------------------+
|  <  PARTIDAS — POLLO                                                         |
+------------------------------------------------------------------------------+
|                                                                              |
|  Partidas remanentes (FIFO — la más vieja se consume primero)                |
|  +------------------------------------------------------------------------+  |
|  | Tanda / fecha   | Proveedor         | Restante | Costo unit. | Subtotal |  |
|  |-----------------|-------------------|----------|-------------|----------|  |
|  | #1 · 10 jul     | Carniceria Lopez  |   1 kg   |  S/. 6,00   | S/. 6,00 |  |
|  | #3 · 12 jul     | Carniceria Lopez  |   5 kg   |  S/. 7,50   | S/. 37,50|  |
|  +------------------------------------------------------------------------+  |
|                                                                              |
|  -----------------------------------------------------------------------     |
|  Stock total:          6 kg                                                  |
|  Valor total (FIFO):   S/. 43,50                                             |
|  -----------------------------------------------------------------------     |
|                                                                              |
|  [ ver trazabilidad completa ]                                               |
+------------------------------------------------------------------------------+
```

- Una fila por **partida remanente**: número de tanda, fecha, proveedor, cantidad restante, costo unitario y subtotal (restante × costo unit.).
- Ordenadas de la más vieja a la más nueva — el orden en que el FIFO las va a agotar.
- Al pie: **stock total** (suma de restantes) y **valor total** (suma de subtotales). Es exactamente el aporte de este producto al widget "Costo de inventario".
- Las partidas agotadas **no aparecen** — esto es la foto del remanente, no el historial (el historial completo está en la trazabilidad).
- Las partidas de ajuste de entrada (sobrante de conteo) aparecen como una partida más, con etiqueta "ajuste" en lugar de proveedor.
- Solo lectura: acá no se edita nada. Los costos se editan en la orden (`orden-compra.md`, Pantalla 6); las cantidades recibidas, en el flujo de partidas del operario.

> PREGUNTA A BACKEND: ¿el remanente por partida se expone ya calculado o el frontend lo deriva de eventos? Asumo: calculado por backend (misma minería que el costo de inventario), recomputable desde cero.

---

## Vista de trazabilidad por producto (actualizada)

Se abre desde "ver trazabilidad por producto" o desde tocar una fila de la tabla. Ahora incluye eventos de tipo PARTIDA y ORDEN.

```
+------------------------------------------------------------------------------+
|  <  Trazabilidad — POLLO                                                     |
+------------------------------------------------------------------------------+
|                                                                              |
|  [ HOY ] [ 7 días ] [ 30 días ] [ personalizado ]                            |
|                                                                              |
|  Stock ahora: 12 kg                                                          |
|  Consumo del período: 58 kg                                                  |
|  Costo consumo (FIFO): S/. 438,86                                             |
|  [ ver partidas remanentes ]                                                 |
|                                                                              |
|  EVENTOS                                                                     |
|  +------------------------------------------------------------------------+  |
|  | Fecha          Tipo         Cantidad    Operario    Nota               |  |
|  |------------------------------------------------------------------------|  |
|  | Ayer 22:30    INVENTARIO    12 kg       Juan                           |  |
|  | Ayer 20:42    PEDIDO         2 un       Juan        salida — terminado  |  |
|  | Ayer 14:35    PARTIDA #3    30 kg       María       Orden Carn. Lopez  |  |
|  | 11 jul 14:05  PARTIDA #2    30 kg       Juan        Orden Carn. Lopez  |  |
|  | 10 jul 16:30  ORDEN          100 kg     Dueño       Carn. Lopez abierta |  |
|  | 10 jul 09:00  INVENTARIO    14 kg       María                          |  |
|  +------------------------------------------------------------------------+  |
|                                                                              |
|  [ descargar CSV ]                                                           |
+------------------------------------------------------------------------------+
```

- Tipos de evento en v0.3: **ORDEN** (pre-carga del dueño), **PARTIDA** (validada por el operario), **PEDIDO** (salida), **INVENTARIO** (conteo).
- Las correcciones se ven como pares: registro corregido con etiqueta y el nuevo con link.
- Las filas de PARTIDA no muestran costo — el costo está en la ORDEN y en la trazabilidad de costos, que es un nivel más.

---

## Celular vertical

Layout apilado, mismos widgets en orden:

```
+----------------------+
| Tablero    Dueño     |
+----------------------+
| [HOY] [7d] [30d]     |
+----------------------+
| POR ACABARSE         |
| PALTA    ●●○ 4       |
| QUESO    ●○○ 0,5 kg  |
| LIMON    ●○○ 2       |
| [ ver todos ]        |
+----------------------+
| PEDIDOS              |
| Terminados   38      |
| Solo foto     5      |
| Total        43      |
+----------------------+
| COSTO INVENTARIO     |
| S/. 2.340,80         |
| plata en depósito    |
+----------------------+
| COSTO CONSUMO        |
| S/. 1.120,50         |
| FIFO · 7d            |
+----------------------+
| ORDENES ABIERTAS     |
| Abiertas        3    |
| Recib. parcial  1    |
| Pendiente S/.1.240   |
| [ver] [+ nueva]      |
+----------------------+
| PRODUCTOS            |
| PALTA                |
|  stock 4 un          |
|  entradas 20 un      |
|  consumo 18 un       |
|  costo S/. 21,60     |
|  ●● por acabar       |
+----------------------+
```

En celular, la tabla se convierte en tarjetas apiladas. Se scrollea todo verticalmente.

---

## Estados

### Vacío (sin registros aún)

```
+------------------------------------------------------------------------------+
|              Todavía no hay registros en este período.                       |
|              Cambiá el rango o esperá a que el operario registre algo.       |
|              [ ver 7 días ]  [ ver 30 días ]                                 |
+------------------------------------------------------------------------------+
```

Los widgets de costo muestran "S/. 0,00" o "—" si no hay órdenes con costo cargado todavía.

### Cargando

Skeletons grises de todos los widgets con la misma forma. Nunca spinner solo.

### Error (al cargar datos)

Banner rojo arriba, no bloqueante, con "[ reintentar ]". Los widgets se pintan con los últimos datos en cache si los hay, en gris con etiqueta "desactualizado".

### Sin conexión

Banner naranja: "Sin conexión — mostrando datos guardados (última sync: hace 12 min)". El tablero muestra el último snapshot cacheado. No bloquea la lectura.

---

## Qué SÍ se muestra (diferencia con el operario)

- Consumo por diferencia en cantidad.
- Stock actual.
- Productos por acabarse (semáforo visual).
- Pedidos del período por estado.
- **Costo de inventario (nuevo):** plata parada en depósito — suma de partidas remanentes, cada una a su costo (FIFO).
- **Costo de consumo del período (nuevo):** plata consumida en el rango, valuada por FIFO.
- **Partidas remanentes por producto (nuevo — revisión FIFO):** fecha/tanda, proveedor, restante, costo unitario y subtotal, con stock y valor total al pie.
- **Órdenes de compra abiertas (nuevo):** cuántas, cuánto falta, acceso a nueva orden.
- Trazabilidad completa de cualquier producto, incluidos eventos PARTIDA y ORDEN.
- Alertas por inconsistencias en los datos.
- Costo de consumo por producto en la tabla.

## Qué NO se muestra en v0.3

- Consumo esperado por receta (fuera de alcance — viene con v0.4).
- Detección automática de fugas (fuera de alcance — viene con recetas).
- Desglose de pedidos por plataforma (v0.2 no lo captura — ver pregunta arriba).
- Comparativas entre operarios.
- Plata en la trazabilidad de eventos: las filas de PARTIDA muestran cantidad, no costo. El costo por partida vive en la vista "Partidas por producto" (remanentes) y en la orden.

---

## Export

Botón "descargar CSV" en la vista principal y en la trazabilidad. Descarga los datos del rango y vista actual. En v0.3 el CSV incluye la columna de costo consumo (FIFO); desde la vista de partidas por producto, el CSV lista las partidas remanentes con restante, costo unitario y subtotal.

> PREGUNTA A BACKEND: ¿el CSV debe respetar el modelo append-only mostrando correcciones como filas separadas con referencia al original, o entregar el "estado final" reconciliado? Asumo por auditoría: append-only, todas las filas, con columna de "corrige a" cuando aplique.

---

## Cómo el dueño arranca una orden nueva

Desde el tablero hay dos accesos directos al flujo de orden de compra:

1. **Botón "+ nueva"** en el widget "Órdenes de compra abiertas" — abre directamente el formulario de nueva orden.
2. **"ver todas las órdenes"** en el mismo widget — abre la lista completa de órdenes, con el botón "+ nueva" arriba a la derecha.

El flujo completo de creación, seguimiento, partidas recibidas, reapertura, anulación y corrección de costos está especificado en `docs/ux/orden-compra.md`.
