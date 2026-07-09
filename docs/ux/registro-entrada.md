# Registro de entrada

## Objetivo del flujo

Que el operario anote qué producto llegó y cuánto, apenas termina de descargar la compra. Sin cálculos, sin totales, sin ver lo que había antes. Sólo cuenta lo que tiene enfrente y lo tipea.

## Usuario

Operario de turno. Manos ocupadas o sucias. Tablet apoyada en la mesada o celular en el bolsillo del delantal.

## Presupuesto

- **Camino feliz:** 3 toques, menos de 5 segundos desde que abre la app.
- **Toque 1:** botón grande "ENTRADA" en el home.
- **Toque 2:** selecciona el producto de la lista (grilla de tarjetas grandes).
- **Toque 3:** tipea cantidad en teclado numérico ya abierto y toca "OK".

El teclado numérico aparece con foco automático — no cuenta como toque. La cantidad tipeada tampoco: los dígitos son parte del toque 3.

## Home (punto de entrada común a los 3 flujos de operario)

Tablet horizontal (1024x768 aprox):

```
+--------------------------------------------------------------+
|  Cocina Control                                Juan  |  cerrar |
+--------------------------------------------------------------+
|                                                              |
|   +------------------+  +------------------+  +------------+ |
|   |                  |  |                  |  |            | |
|   |     ENTRADA      |  |      CIERRE      |  |   PEDIDO   | |
|   |                  |  |                  |  |            | |
|   |    (llegó algo)  |  |   (fin turno)    |  | (Rappi/PY) | |
|   |                  |  |                  |  |            | |
|   +------------------+  +------------------+  +------------+ |
|                                                              |
|                                          [ver mis registros] |
+--------------------------------------------------------------+
```

Celular vertical (360x780 aprox):

```
+----------------------+
| Cocina Control  Juan |
+----------------------+
|                      |
| +------------------+ |
| |                  | |
| |     ENTRADA      | |
| |                  | |
| +------------------+ |
|                      |
| +------------------+ |
| |                  | |
| |     CIERRE       | |
| |                  | |
| +------------------+ |
|                      |
| +------------------+ |
| |     PEDIDO       | |
| +------------------+ |
|                      |
| [ver mis registros]  |
+----------------------+
```

Los tres botones ocupan como mínimo 1/3 del alto útil. Color plano, texto en mayúsculas grandes. Nada más. El "ver mis registros" es texto chico abajo — es la puerta a las correcciones.

## Pantalla 1 — Selección de producto

Se abre después del toque 1. Grilla de tarjetas por producto, ordenadas por uso más frecuente (más usadas arriba).

Tablet horizontal:

```
+--------------------------------------------------------------+
|  <  ENTRADA — ¿qué llegó?                                    |
+--------------------------------------------------------------+
|                                                              |
|  +--------+  +--------+  +--------+  +--------+  +--------+  |
|  | PALTA  |  | POLLO  |  |TOMATE  |  |CEBOLLA |  | QUESO  |  |
|  +--------+  +--------+  +--------+  +--------+  +--------+  |
|                                                              |
|  +--------+  +--------+  +--------+  +--------+  +--------+  |
|  | YOGURT |  | PAN    |  | ACEITE |  | ARROZ  |  | LIMON  |  |
|  +--------+  +--------+  +--------+  +--------+  +--------+  |
|                                                              |
|  [ buscar producto _______________________ ]                 |
+--------------------------------------------------------------+
```

Cada tarjeta: nombre del producto en mayúsculas, tamaño mínimo 120x120 en tablet, 90x90 en celular. Nada más — ni stock, ni ícono decorativo. La búsqueda queda abajo, sólo se usa si el producto no está a la vista.

Celular vertical: grilla de 2 columnas, mismo criterio (más usadas arriba). Se scrollea.

> PREGUNTA A BACKEND: ¿el catálogo de productos ya existe o el operario también puede crear productos nuevos desde acá? Por ahora asumo catálogo cerrado, cargado por el dueño. Si el producto no está, el operario no puede registrar.

## Pantalla 2 — Cantidad

Se abre después del toque 2. Nombre del producto arriba, teclado numérico grande abajo, foco automático en el campo. Sin unidad prellenada, sin sugerencia de cantidad, sin "esperado".

Tablet horizontal:

```
+--------------------------------------------------------------+
|  <  ENTRADA — PALTA                                          |
+--------------------------------------------------------------+
|                                                              |
|                    Cantidad que llegó                        |
|                                                              |
|                    +----------------+                        |
|                    |      12        |  [unidad v]            |
|                    +----------------+                        |
|                                                              |
|            +-----+  +-----+  +-----+                         |
|            |  7  |  |  8  |  |  9  |                         |
|            +-----+  +-----+  +-----+                         |
|            +-----+  +-----+  +-----+                         |
|            |  4  |  |  5  |  |  6  |                         |
|            +-----+  +-----+  +-----+                         |
|            +-----+  +-----+  +-----+                         |
|            |  1  |  |  2  |  |  3  |                         |
|            +-----+  +-----+  +-----+                         |
|            +-----+  +-----+  +-----+                         |
|            |  0  |  |  ,  |  |  <x |                         |
|            +-----+  +-----+  +-----+                         |
|                                                              |
|                    [       OK        ]                       |
+--------------------------------------------------------------+
```

El selector de unidad (kg / unidades / litros) sale al lado del número, prellenado con la unidad configurada del producto. Si el producto tiene una sola unidad posible, no aparece el selector.

> PREGUNTA A BACKEND: ¿cada producto tiene una única unidad definida en el catálogo, o el operario elige entre varias al registrar? Asumo: unidad única por producto, definida por el dueño. El operario no elige.

Celular vertical: mismo layout, teclado ocupa mitad inferior de la pantalla. Botón OK sticky abajo.

## Estados

### Vacío (no hay productos en el catálogo)

```
+--------------------------------------------------------------+
|  <  ENTRADA                                                  |
+--------------------------------------------------------------+
|                                                              |
|                No hay productos cargados.                    |
|                Pedile al dueño que los cargue.               |
|                                                              |
+--------------------------------------------------------------+
```

### Cargando (cuando se abre la grilla de productos)

Skeletons de tarjetas grises, mismo tamaño y grilla. Nunca spinner centrado — mantiene la forma para que el operario ya sepa dónde va a tocar.

### Error (al guardar)

Toast rojo abajo, no bloqueante para el input:

```
+--------------------------------------------------------------+
|  No se pudo guardar. Tocá de nuevo OK.                       |
+--------------------------------------------------------------+
```

El botón OK vuelve a estar activo. La cantidad tipeada NO se pierde.

### Éxito

Transición instantánea a una pantalla de confirmación de 1.5 segundos y vuelta al home:

```
+--------------------------------------------------------------+
|                                                              |
|                   [ tilde grande verde ]                     |
|                                                              |
|                   ENTRADA REGISTRADA                         |
|                   PALTA — 12 unidades                        |
|                                                              |
|                    [   corregir   ]  [   listo   ]           |
|                                                              |
+--------------------------------------------------------------+
```

Botón "listo" o timer de 1.5s vuelven al home. "Corregir" abre el flujo de corrección (ver más abajo). Este confirmatorio es la ÚNICA vez que el operario ve lo que acaba de anotar. Después no lo vuelve a ver.

### Sin conexión

Banner naranja arriba, no bloquea el flujo:

```
+--------------------------------------------------------------+
|  Sin conexión — se guarda cuando vuelva                      |
+--------------------------------------------------------------+
|  <  ENTRADA — ¿qué llegó?                                    |
| ...                                                          |
```

El registro se guarda local y se sincroniza cuando vuelve la red. El confirmatorio se muestra igual. El operario no espera al servidor.

> PREGUNTA A BACKEND: ¿está definido el modelo offline-first? Asumo que sí (registros append-only con id local + sync posterior). Si backend dice que no, rediseñamos la confirmación para que espere al servidor.

## Correcciones

Un registro NUNCA se edita ni se borra. Corregir es hacer un registro nuevo que apunta al anterior.

### Puerta 1: desde el confirmatorio

Botón "corregir" en la pantalla de éxito. Sólo aparece durante los 1.5 segundos del confirmatorio.

### Puerta 2: desde "mis registros" en el home

Abre una lista de los registros del operario en el turno actual, más nuevos arriba:

```
+--------------------------------------------------------------+
|  <  Mis registros de hoy                                     |
+--------------------------------------------------------------+
|  14:32   ENTRADA   PALTA        12 un.       [corregir]      |
|  14:15   ENTRADA   QUESO         5 kg        [corregir]      |
|  13:50   PEDIDO    Rappi                     [corregir]      |
|  13:20   ENTRADA   POLLO        20 kg        [corregido]     |
|          └─ corrección: 22 kg (14:05)                        |
+--------------------------------------------------------------+
```

Los registros ya corregidos se muestran en gris con la etiqueta "corregido" y su reemplazo debajo indentado. No se puede corregir dos veces la misma cadena — se corrige siempre el último eslabón.

> PREGUNTA A BACKEND: ¿cuál es la ventana temporal en la que un operario puede corregir sus propios registros? ¿Sólo su turno? ¿24 horas? ¿Siempre? Asumo: turno actual. Después de cerrar turno sólo el dueño corrige.

### Pantalla de corrección

Se abre al tocar "corregir". Misma pantalla de cantidad pero con banner arriba indicando qué corrige:

```
+--------------------------------------------------------------+
|  <  CORRIGIENDO — PALTA (antes: 12 un.)                      |
+--------------------------------------------------------------+
|                                                              |
|                Nueva cantidad                                |
|                                                              |
|                +----------------+                            |
|                |      15        |  unidades                  |
|                +----------------+                            |
|                                                              |
|                [ teclado numérico ]                          |
|                                                              |
|                [       OK        ]                           |
+--------------------------------------------------------------+
```

Esta es la ÚNICA pantalla del flujo de operario donde ve un dato numérico previo. Es inevitable — necesita saber qué está corrigiendo. No es un "total" ni un "consumo", es la referencia al hecho anterior.

Al confirmar, se crea un registro nuevo que en el modelo apunta al id del registro corregido. El anterior queda intacto.

## Qué NO se muestra nunca en este flujo

- Stock actual del producto.
- Cuánto se anotó antes en este turno o en turnos previos.
- Cuánto "se esperaba" que llegara.
- Totales, promedios, consumos.
