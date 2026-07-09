# Tablero del dueño (v0.2)

## Objetivo del flujo

Que el dueño, de un solo vistazo, vea el estado del inventario: consumo por diferencia del último período, stock actual y productos por acabarse. Cero acciones necesarias — sólo lectura. Es la contracara de las pantallas del operario: acá SÍ hay totales, promedios, comparativas y consumos.

Alineado con el principio rector de v0.2: la captura (entregas verificadas, fotos de pedidos, conteos) optimiza fidelidad; este tablero es la minería posterior sobre esos datos crudos.

## Usuario

Dueño de la cocina. Mira desde el escritorio, en pausa entre tareas. Prioriza velocidad de lectura sobre densidad de datos. Puede entrar a detalle si algo le llama la atención.

## Presupuesto

No aplica el techo de 3 toques / 5 segundos — no es un flujo de captura. La meta acá es distinta:

- **Vista principal legible en menos de 3 segundos.**
- **Producto por acabarse identificable de un vistazo (visual, no textual).**

## Acceso

- Sólo el dueño ve este tablero. Login separado del operario o rol distinto en el mismo login.
- El operario nunca ve este tablero. Ni siquiera un link o preview.
- Desde acá el dueño también **pre-carga las entregas** (ver registro-entrada.md) y **pide conteos de inventario** (ver registro-inventario.md). Esas pantallas de administración se especifican aparte cuando se diseñe el panel del dueño; este documento cubre la vista de lectura.

> PREGUNTA A BACKEND: ¿existe el concepto de rol (operario vs dueño) en el modelo de usuarios de v0.2, o hay una app distinta por rol? Asumo: mismo login, distinto rol. El rol "operario" nunca puede acceder a la ruta del tablero.

## Vista principal

Pensada para pantalla grande (desktop 1440+) o tablet horizontal. En celular vertical se apila y el widget de "por acabarse" queda arriba de todo.

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
|  CONSUMO Y STOCK POR PRODUCTO                                                |
|  +------------------------------------------------------------------------+  |
|  | Producto  | Stock ahora | Entradas | Consumo (diff) | Alerta         |  |
|  |-----------|-------------|----------|----------------|----------------|  |
|  | PALTA     |     4 un    |   20 un  |    18 un       |  ●● por acabar |  |
|  | POLLO     |    12 kg    |   30 kg  |    22 kg       |                |  |
|  | TOMATE    |     8 kg    |   15 kg  |    12 kg       |                |  |
|  | CEBOLLA   |     3 kg    |   10 kg  |     9 kg       |                |  |
|  | QUESO     |   0,5 kg    |    5 kg  |     6 kg  ⚠   |  ●   por acabar |  |
|  +------------------------------------------------------------------------+  |
|                                                                              |
|  [ descargar CSV ]                       [ ver trazabilidad por producto ]   |
+------------------------------------------------------------------------------+
```

### Widget "por acabarse" (arriba a la izquierda)

- Lista corta, máximo 5 productos.
- Semáforo visual por producto: círculos llenos/vacíos ● ○ ○ indicando nivel relativo al umbral. Verde = ok, amarillo = advertencia, rojo = crítico.
- El valor numérico (stock) al lado, secundario visualmente. Lo importante es el color.
- "Ver todos" abre la tabla completa filtrada por productos bajo umbral.

> PREGUNTA A BACKEND: ¿el umbral "por acabarse" es fijo por producto (definido por el dueño en el catálogo), calculado por consumo promedio, o híbrido? Asumo por ahora: fijo, cargado por el dueño en el catálogo. Si no está cargado, no aparece en "por acabarse" pero sí en la tabla.

### Widget "pedidos en el período" (arriba a la derecha)

- Conteo de pedidos por **estado**: terminados (con detalle de productos) y solo-foto (pendientes sin completar). Total abajo.
- Un número alto de "solo foto" persistente es señal para el dueño de que el detalle no se está completando — y su análisis de salidas pierde granularidad.
- No abre detalle en v0.2 — es sólo lectura rápida.

> PREGUNTA A BACKEND (y al dueño): v0.2 no captura la plataforma (Rappi / PedidosYa) en el flujo del operario. ¿El dueño necesita el desglose por plataforma antes de que lleguen las integraciones por API? Si sí, se agrega como toque opcional en "completar pedido".

### Tabla "consumo y stock por producto" (abajo)

Una fila por producto activo del catálogo. Columnas:

- **Producto** — nombre en mayúsculas.
- **Stock ahora** — último inventario registrado, ajustado por entregas validadas posteriores.
- **Entradas** — suma de lo recibido en entregas **validadas** en el rango elegido (el valor recibido, no el anunciado).
- **Consumo (diff)** — cálculo: `stock inicial + entradas − stock actual`. Es el consumo por diferencia que exige el requerimiento.
- **Alerta** — semáforo visual si el consumo tiene diferencias anómalas o si el stock está bajo el umbral.

Ordenada por defecto por "alerta" descendente (primero los que tienen algo raro), después por consumo descendente.

> PREGUNTA A BACKEND: la fórmula de consumo por diferencia necesita un "stock de inicio del período". ¿Se toma el último inventario anterior al inicio del rango, o el primero dentro del rango? Asumo: último inventario anterior. Si no existe, se muestra "sin dato de inicio" en esa fila y el consumo queda vacío.

> PREGUNTA A BACKEND: ¿qué dispara el ícono de advertencia "⚠" en la columna de consumo? En v0.2 asumo sólo casos matemáticamente imposibles (consumo negativo, stock actual mayor que stock inicial + entradas). Alertas por desviación quedan para cuando haya recetas. Los productos marcados en pedidos terminados habilitan, a futuro, cruzar salidas declaradas contra consumo por diferencia — es minería posterior, no entra en v0.2.

### Selector de período (arriba)

- HOY: desde el último inventario hasta ahora.
- 7 días: últimos 7 días completos.
- 30 días: últimos 30 días completos.
- Personalizado: date pickers de inicio y fin.

Cambio de período recarga la vista completa.

## Vista de trazabilidad por producto

Se abre desde el link inferior "ver trazabilidad por producto" o desde tocar una fila de la tabla.

```
+------------------------------------------------------------------------------+
|  <  Trazabilidad — PALTA                                                     |
+------------------------------------------------------------------------------+
|                                                                              |
|  [ HOY ] [ 7 días ] [ 30 días ] [ personalizado ]                            |
|                                                                              |
|  Stock ahora: 4 un.                                                          |
|  Consumo del período: 18 un.                                                 |
|                                                                              |
|  EVENTOS                                                                     |
|  +------------------------------------------------------------------------+  |
|  | Fecha          Tipo        Cantidad   Operario   Nota                  |  |
|  |------------------------------------------------------------------------|  |
|  | Ayer 22:30    INVENTARIO    4 un      Juan                             |  |
|  | Ayer 20:42    PEDIDO        2 un      Juan       salida — pedido term. |  |
|  | Ayer 14:35    ENTREGA      15 un      Juan       corrige el de 14:32   |  |
|  | Ayer 14:32    ENTREGA      12 un      Juan       corregido → 15 un     |  |
|  | Ayer 09:00    INVENTARIO   10 un      María                            |  |
|  +------------------------------------------------------------------------+  |
|                                                                              |
|  [ descargar CSV ]                                                           |
+------------------------------------------------------------------------------+
```

- Todos los eventos que tocaron ese producto en el rango, más nuevos arriba. Tipos en v0.2: **ENTREGA** (validada, con anunciado vs recibido), **PEDIDO** (productos declarados al completar), **INVENTARIO** (conteos).
- Las correcciones se ven como pares: el registro corregido con etiqueta y el nuevo mostrando el link.
- Las filas PEDIDO son salidas declaradas — informativas; el consumo oficial sigue siendo por diferencia.
- Cumple el criterio de aceptación "el dueño puede reconstruir la trazabilidad completa de cualquier producto".

## Celular vertical

El dueño puede mirar desde el celular. Layout apilado, mismos widgets en orden:

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
| PRODUCTOS            |
| PALTA                |
|  stock 4 un          |
|  entradas 20 un      |
|  consumo 18 un       |
|  ●● por acabar       |
+----------------------+
```

En celular, la tabla se convierte en tarjetas apiladas. Se scrollea todo verticalmente.

## Estados

### Vacío (sin registros aún)

```
+------------------------------------------------------------------------------+
|              Todavía no hay registros en este período.                       |
|              Cambiá el rango o esperá a que el operario registre algo.       |
|              [ ver 7 días ]  [ ver 30 días ]                                 |
+------------------------------------------------------------------------------+
```

### Cargando

Skeletons grises de los tres widgets con la misma forma. Nunca spinner solo.

### Error (al cargar datos)

Banner rojo arriba, no bloqueante, con "[ reintentar ]". Los widgets se pintan con los últimos datos en cache si los hay, en gris con etiqueta "desactualizado".

### Sin conexión

Banner naranja: "Sin conexión — mostrando datos guardados (última sync: hace 12 min)". El tablero muestra el último snapshot cacheado. No bloquea la lectura.

## Qué SÍ se muestra (a diferencia de operario)

- Consumo por diferencia.
- Stock actual.
- Productos por acabarse (semáforo visual).
- Pedidos del período por estado (terminados / solo foto).
- Trazabilidad completa de cualquier producto, fotos de pedidos incluidas.
- Alertas por inconsistencias en los datos.

## Qué NO se muestra en v0.2

- Consumo esperado por receta (fuera de alcance, hay que definir recetas).
- Detección automática de fugas (fuera de alcance, viene con recetas).
- Desglose de pedidos por plataforma (v0.2 no lo captura — ver pregunta arriba).
- Costos, márgenes, ingresos (no está en requerimientos).
- Comparativas entre operarios (posible más adelante, no está pedido).

## Export

Botón "descargar CSV" en la vista principal y en la trazabilidad. Descarga los datos del rango y vista actual. Es la salida cruda si el dueño quiere procesar en Excel.

> PREGUNTA A BACKEND: ¿el CSV debe respetar el modelo append-only mostrando correcciones como filas separadas con referencia al original, o entregar el "estado final" reconciliado? Asumo por auditoría: append-only, todas las filas, con columna de "corrige a" cuando aplique. Para entregas, incluye columnas de anunciado y recibido.
