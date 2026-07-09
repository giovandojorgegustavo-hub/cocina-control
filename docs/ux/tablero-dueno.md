# Tablero del dueño

## Objetivo del flujo

Que el dueño, de un solo vistazo, vea el estado del inventario: consumo por diferencia del último período, stock actual y productos por acabarse. Cero acciones necesarias — sólo lectura. Es la contracara de las pantallas del operario: acá SÍ hay totales, promedios, comparativas y consumos.

## Usuario

Dueño de la cocina. Mira desde el escritorio, en pausa entre tareas. Prioriza velocidad de lectura sobre densidad de datos. Puede entrar a detalle si algo le llama la atención.

## Presupuesto

No aplica el techo de 3 toques / 5 segundos — no es un flujo de captura. La meta acá es distinta:

- **Vista principal legible en menos de 3 segundos.**
- **Producto por acabarse identificable de un vistazo (visual, no textual).**

## Acceso

- Sólo el dueño ve este tablero. Login separado del operario o rol distinto en el mismo login.
- El operario nunca ve este tablero. Ni siquiera un link o preview.

> PREGUNTA A BACKEND: ¿existe el concepto de rol (operario vs dueño) en el modelo de usuarios de v0.1, o hay una app distinta por rol? Asumo: mismo login, distinto rol. El rol "operario" nunca puede acceder a la ruta del tablero.

## Vista principal

Pensada para pantalla grande (desktop 1440+) o tablet horizontal. En celular vertical se apila y el widget de "por acabarse" queda arriba de todo.

Desktop / tablet horizontal:

```
+------------------------------------------------------------------------------+
|  Cocina Control — Tablero                             Dueño  |  cerrar sesión |
+------------------------------------------------------------------------------+
|                                                                              |
|  [ HOY ] [ 7 días ] [ 30 días ] [ personalizado ]     último cierre: ayer 23:15 |
|                                                                              |
|  +-------------------------------+  +-----------------------------------+    |
|  |  POR ACABARSE                 |  |  PEDIDOS EN EL PERÍODO            |    |
|  |                               |  |                                   |    |
|  |  PALTA         ●●○ 4 un.      |  |  Rappi           23                |    |
|  |  QUESO         ●○○ 0,5 kg     |  |  PedidosYa       18                |    |
|  |  LIMON         ●○○ 2 un.      |  |  Otro             2                |    |
|  |                               |  |                                   |    |
|  |  [ ver todos ]                |  |  Total           43                |    |
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
|  | ...       |             |          |                |                |  |
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

- Conteo simple de pedidos por plataforma en el rango elegido.
- Total abajo.
- No abre detalle en v0.1 — es sólo lectura rápida.

### Tabla "consumo y stock por producto" (abajo)

Una fila por producto activo del catálogo. Columnas:

- **Producto** — nombre en mayúsculas.
- **Stock ahora** — último cierre registrado, o entrada más reciente si nunca hubo cierre.
- **Entradas** — suma de todo lo registrado como entrada en el rango elegido.
- **Consumo (diff)** — cálculo: `stock inicial + entradas − stock actual`. Es el consumo por diferencia que exige el requerimiento.
- **Alerta** — semáforo visual si el consumo tiene diferencias anómalas con lo esperado, o si el stock está bajo el umbral.

Ordenada por defecto por "alerta" descendente (primero los que tienen algo raro), después por consumo descendente.

> PREGUNTA A BACKEND: la fórmula de consumo por diferencia (`stock_inicio + entradas − stock_actual`) necesita un "stock de inicio del período". ¿Se toma el último cierre anterior al inicio del rango, o el primer cierre dentro del rango? Asumo: último cierre anterior. Si no existe cierre previo, se muestra "sin dato de inicio" en esa fila y el consumo queda vacío.

> PREGUNTA A BACKEND: ¿qué disparara el ícono de advertencia "⚠" en la columna de consumo? ¿Consumo mayor que entradas + stock inicial (imposible)? ¿Consumo negativo? ¿Desviación respecto al promedio histórico? En v0.1 asumo sólo casos imposibles matemáticamente (ej. consumo negativo, stock actual mayor que stock inicial + entradas). Alertas por desviación quedan para cuando haya recetas.

### Selector de período (arriba)

- HOY: desde el último cierre de ayer hasta ahora.
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
|  | Fecha          Tipo      Cantidad   Operario   Nota                    |  |
|  |------------------------------------------------------------------------|  |
|  | Ayer 22:30    CIERRE      4 un      Juan                               |  |
|  | Ayer 14:32    ENTRADA    12 un      Juan       corregido → 15 un       |  |
|  | Ayer 14:35    ENTRADA    15 un      Juan       corrige el de 14:32     |  |
|  | Ayer 09:00    CIERRE     10 un      María                              |  |
|  | ...                                                                    |  |
|  +------------------------------------------------------------------------+  |
|                                                                              |
|  [ descargar CSV ]                                                           |
+------------------------------------------------------------------------------+
```

- Todos los eventos que tocaron ese producto en el rango, más nuevos arriba.
- Las correcciones se ven como pares: el registro corregido con etiqueta y el nuevo debajo (o al lado, con flecha) mostrando el link.
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
| Rappi        23      |
| PedidosYa    18      |
| Otro          2      |
| Total        43      |
+----------------------+
| PRODUCTOS            |
| PALTA                |
|  stock 4 un          |
|  entradas 20 un      |
|  consumo 18 un       |
|  ●● por acabar       |
+----------------------+
| POLLO                |
|  stock 12 kg         |
|  ...                 |
+----------------------+
```

En celular, la tabla se convierte en tarjetas apiladas. Se scrollea todo verticalmente.

## Estados

### Vacío (sin registros aún)

Ocurre en los primeros días de uso o si nadie registró nada en el período elegido:

```
+------------------------------------------------------------------------------+
|  Tablero — HOY                                                               |
+------------------------------------------------------------------------------+
|                                                                              |
|              Todavía no hay registros en este período.                       |
|              Cambiá el rango o esperá a que el operario registre algo.       |
|                                                                              |
|              [ ver 7 días ]  [ ver 30 días ]                                 |
|                                                                              |
+------------------------------------------------------------------------------+
```

### Cargando

Skeletons grises de los tres widgets con la misma forma. Nunca spinner solo.

### Error (al cargar datos)

Banner rojo arriba, no bloqueante:

```
+------------------------------------------------------------------------------+
|  No se pudo cargar el tablero.  [ reintentar ]                               |
+------------------------------------------------------------------------------+
```

Los widgets se pintan con los últimos datos en cache si los hay, en gris con etiqueta "desactualizado".

### Éxito

Es el estado por defecto. No hay confirmatorio — es sólo lectura.

### Sin conexión

Banner naranja arriba:

```
+------------------------------------------------------------------------------+
|  Sin conexión — mostrando datos guardados (última sync: hace 12 min)         |
+------------------------------------------------------------------------------+
```

El tablero muestra el último snapshot cacheado, con la marca de tiempo de la última sync. No bloquea la lectura.

## Qué SÍ se muestra (a diferencia de operario)

- Consumo por diferencia.
- Stock actual.
- Productos por acabarse (semáforo visual).
- Conteo de pedidos por plataforma.
- Trazabilidad completa de cualquier producto.
- Alertas por inconsistencias en los datos.

## Qué NO se muestra en v0.1

- Consumo esperado por receta (fuera de alcance, hay que definir recetas).
- Detección automática de fugas (fuera de alcance, viene con recetas).
- Costos, márgenes, ingresos por plataforma (no está en requerimientos).
- Comparativas entre operarios (posible en v0.2, no está pedido en v0.1).

## Export

Botón "descargar CSV" en la vista principal y en la trazabilidad. Descarga los datos del rango y vista actual. Es la salida cruda si el dueño quiere procesar en Excel.

> PREGUNTA A BACKEND: ¿el CSV debe respetar el modelo append-only mostrando correcciones como filas separadas con referencia al original, o debe entregar el "estado final" ya reconciliado (una fila por evento, con la última corrección aplicada)? Asumo por auditoría: append-only, todas las filas, con columna de "corrige a" cuando aplique.
