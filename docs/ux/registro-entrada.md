# Registro de entrada (v0.2 — verificación de entregas)

## Objetivo del flujo

Que el operario verifique una entrega que el dueño ya anunció, en vez de cargarla desde cero. El dueño pre-carga qué compró (productos y cantidades); el operario compara contra lo que tiene enfrente y confirma o corrige. El stock impacta recién cuando valida la entrega completa.

## Usuarios

- **Dueño:** pre-carga cada entrega esperada (proveedor, productos, cantidades anunciadas) desde su panel. Esa pantalla es del tablero del dueño, no de este flujo.
- **Operario de turno:** manos ocupadas o sucias. Tablet apoyada en la mesada o celular en el bolsillo del delantal. Verifica, no carga.

## Presupuesto

- **Camino feliz (llegó exactamente lo anunciado):** 1 toque por producto, menos de 2 segundos cada uno.
- **Toque 1:** botón grande "ENTRADA" en el home.
- **Toque 2:** la entrega no leída en la bandeja.
- **Toques 3..N+2:** "OK — llegó así" por cada producto (el default anunciado ya está puesto).
- **Toque final:** "validar entrega".

Sólo se tipea cuando la realidad difiere de lo anunciado. Ahí el teclado numérico aparece con foco automático y el default editable.

## Home (punto de entrada común a los 3 flujos de operario)

Tablet horizontal (1024x768 aprox):

```
+--------------------------------------------------------------+
|  Cocina Control                                Juan  |  cerrar |
+--------------------------------------------------------------+
|                                                              |
|   +------------------+  +------------------+  +------------+ |
|   |                  |  |                  |  |            | |
|   |     ENTRADA      |  |   INVENTARIO     |  |   PEDIDO   | |
|   |                  |  |                  |  |            | |
|   | (llegó una       |  |  (contar stock)  |  | (foto al   | |
|   |     entrega)     |  |                  |  |  empacar)  | |
|   +------------------+  +------------------+  +------------+ |
|                                                              |
|                                          [ver mis registros] |
+--------------------------------------------------------------+
```

Los tres botones ocupan como mínimo 1/3 del alto útil. Color plano, texto en mayúsculas grandes. El "ver mis registros" es texto chico abajo — es la puerta a las correcciones posteriores.

Celular vertical (360x780 aprox): mismos tres botones apilados, cada uno ~1/4 del alto útil.

## Pantalla 1 — Bandeja de entregas

Se abre después del toque 1. Lista de entregas pre-cargadas por el dueño, más nuevas arriba.

```
+--------------------------------------------------------------+
|  <  ENTRADA — entregas                                       |
+--------------------------------------------------------------+
|  +--------------------------------------------------------+  |
|  |  VERDULERIA NUÑEZ                        [ NO LEIDO ]  |  |
|  |  hoy 14:00  ·  8 productos                             |  |
|  +--------------------------------------------------------+  |
|  +--------------------------------------------------------+  |
|  |  CARNICERIA LOPEZ  (gris)               [ validado ✓ ] |  |
|  |  hoy 09:30  ·  3 productos                             |  |
|  +--------------------------------------------------------+  |
|  +--------------------------------------------------------+  |
|  |  DISTRIBUIDORA SUR  (gris)              [ validado ✓ ] |  |
|  |  ayer 16:45  ·  5 productos                            |  |
|  +--------------------------------------------------------+  |
+--------------------------------------------------------------+
```

- **Estados de entrega: no leído → validado.** La entrega nueva aparece con badge oscuro "NO LEÍDO" y borde fuerte. Las validadas bajan a gris con "validado ✓".
- Tocar una entrega no leída abre la verificación (pantalla 2). Tocar una validada abre su detalle en modo lectura (con puerta de corrección).
- No hay estado intermedio "a medias" visible en la bandeja: si el operario abandonó una verificación, la entrega sigue no leída y conserva lo ya confirmado.

> PREGUNTA A BACKEND: ¿una entrega anunciada puede editarse (el dueño) después de publicada? ¿Qué pasa si el operario ya la abrió? Asumo: editable mientras esté no leída; al validarse, se congela.

## Pantalla 2 — Verificación de la entrega

La lista pre-cargada, un producto por fila, con la cantidad anunciada como **default editable**. El primer producto pendiente queda resaltado con foco.

```
+--------------------------------------------------------------+
|  <  ENTRADA — Verduleria Nuñez                               |
+--------------------------------------------------------------+
|    PALTA      12 un.                                   ✓     |
|    POLLO      20 kg                                    ✓     |
|    TOMATE     12 kg  (anunciado: 15 kg)                ✓     |
|  ▶ CEBOLLA    10 kg     [ OK — llegó así ]  [ editar ]       |
|    QUESO      5 kg                                           |
|    LIMON      30 un.                                         |
|                                                              |
|  al validar, la entrega impacta el stock                     |
|                              [ validar entrega  (3/8) ]      |
+--------------------------------------------------------------+
```

- **Flujo optimista:** "OK — llegó así" confirma el default y salta al siguiente pendiente. Un toque por producto.
- **"editar"** abre la pantalla de cantidad (pantalla 3) con el default precargado.
- Los confirmados bajan a gris con tilde verde. Si se editó, muestra el recibido y el anunciado entre paréntesis: quedan **ambos valores**, nunca se pisa el anunciado.
- El botón "validar entrega (3/8)" muestra el progreso y queda deshabilitado hasta confirmar todos los productos.
- **Al validar, la entrega impacta el stock.** Antes de eso, nada de lo confirmado afecta ningún número del sistema.

> PREGUNTA A BACKEND: ¿qué hace el operario si llegó un producto que NO está en la lista anunciada? Asumo v0.2: no puede agregar ítems a la entrega; le avisa al dueño por fuera y el dueño corrige la entrega. Si esto resulta frecuente, se diseña "agregar producto no anunciado" en v0.3.

> PREGUNTA A BACKEND: ¿un producto puede llegar en cantidad 0 (no vino)? Asumo: sí — el operario edita a 0; queda anunciado vs. recibido = 0.

## Pantalla 3 — Editar cantidad

Sólo se abre cuando la realidad difiere del anuncio. Default precargado, foco automático, teclado numérico grande.

```
+--------------------------------------------------------------+
|  <  ENTRADA — CEBOLLA  (anunciado: 10 kg)                    |
+--------------------------------------------------------------+
|                                                              |
|                 Cantidad recibida                            |
|                                                              |
|                 +----------------+                           |
|                 |       8        |   kg                      |
|                 +----------------+                           |
|                                                              |
|                 [ teclado numérico ]                         |
|                                                              |
|                 [    OK y siguiente  →    ]                  |
+--------------------------------------------------------------+
```

El anunciado queda visible en el header como referencia — es parte del hecho a verificar, no un análisis. "OK y siguiente" guarda y salta al próximo pendiente de la lista.

## Pantalla 4 — Entrega validada

Confirmatorio de 1.5 segundos y vuelta al home:

```
+--------------------------------------------------------------+
|                                                              |
|                   [ tilde grande verde ]                     |
|                                                              |
|                   ENTREGA VALIDADA                           |
|          Verduleria Nuñez — 8 productos → stock actualizado  |
|                                                              |
|                        [   listo   ]                         |
|                                                              |
+--------------------------------------------------------------+
```

## Estados

### Vacío (no hay entregas anunciadas)

```
+--------------------------------------------------------------+
|  <  ENTRADA — entregas                                       |
+--------------------------------------------------------------+
|                                                              |
|            No hay entregas anunciadas.                       |
|            Cuando el dueño cargue una, aparece acá.          |
|                                                              |
+--------------------------------------------------------------+
```

### Cargando

Skeletons con la forma de las filas de la bandeja. Nunca spinner centrado.

### Error (al validar)

Toast rojo abajo, no bloqueante. Lo confirmado NO se pierde:

```
+--------------------------------------------------------------+
|  No se pudo validar. Tocá de nuevo.                          |
+--------------------------------------------------------------+
```

### Sin conexión

Banner naranja arriba, no bloquea. Confirmaciones y validación se guardan local y se sincronizan al volver la red. El confirmatorio se muestra igual — el operario no espera al servidor.

```
+--------------------------------------------------------------+
|  Sin conexión — se guarda cuando vuelva                      |
+--------------------------------------------------------------+
```

> PREGUNTA A BACKEND: si dos dispositivos validan la misma entrega offline, ¿quién gana? Asumo: primera validación en llegar al servidor gana; la segunda se descarta con aviso.

## Correcciones

Un registro NUNCA se edita ni se borra. Corregir es crear un registro nuevo que apunta al anterior.

- **Antes de validar:** tocar un producto ya confirmado permite re-confirmarlo o re-editarlo. Como la entrega todavía no impactó stock, esto es parte de la verificación, no una corrección formal.
- **Después de validar:** desde "ver mis registros" del home (o desde la entrega validada en la bandeja), el operario puede corregir la cantidad recibida de un producto. Eso crea un registro nuevo apuntando al original, y el stock se recalcula.

> PREGUNTA A BACKEND: ¿cuál es la ventana en la que el operario puede corregir una entrega validada? Asumo: mientras esté logueado ese día. Después, sólo el dueño.

## Qué NO se muestra nunca en este flujo

- Stock actual del producto.
- Totales, promedios, consumos.
- Historial de entregas de otros días (sólo la bandeja reciente).

La lista pre-cargada con sus cantidades anunciadas **no** viola el principio de "contar a ciegas": es el hecho declarado que el operario debe verificar, no un cálculo del sistema.
