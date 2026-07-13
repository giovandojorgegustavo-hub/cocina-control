# Registro de entrada (v0.3 — verificación de partidas de orden)

> **Qué cambió respecto de v0.2:**
> - La "entrega" pasa a llamarse **orden de compra**. Una orden puede recibirse en varias **partidas**.
> - La bandeja muestra órdenes en estado **abierta** (nunca llegó nada) y **recibida parcialmente** (algo llegó, falta el resto). Las órdenes cerradas y anuladas NO aparecen en la bandeja activa — solo en el historial del dueño.
> - Al abrir una orden, el operario ve el **saldo pendiente por producto**, no la cantidad total original.
> - "OK — llegó así" en v0.3 significa "llegó todo el pendiente de este producto en esta partida". Si difiere, edita.
> - Si toda la orden queda en saldo 0 al validar, el cierre es automático — el operario solo ve "orden completa".
> - **Regla no negociable:** el operario nunca ve costo, precio ni total en soles. Verificable a simple vista en cualquier wireframe de este documento.
> - El flujo de 1 toque por producto (caso feliz) se mantiene igual que v0.2.

---

## Objetivo del flujo

Que el operario registre una partida de una orden de compra: producto por producto, confirma lo que llegó en esta tanda específica. El dueño ya pre-cargó la orden; el operario no carga nada desde cero. El stock impacta al validar la partida completa.

## Usuarios

- **Dueño:** pre-carga la orden de compra (proveedor, productos, cantidades esperadas) desde su panel. Ese flujo está en `orden-compra.md`.
- **Operario de turno:** manos ocupadas o sucias. Tablet apoyada en la mesada o celular en el bolsillo del delantal. Verifica lo que llegó hoy en esta tanda.

## Presupuesto

- **Camino feliz (llegó exactamente lo pendiente de cada producto):** 1 toque por producto, menos de 2 segundos cada uno.
- **Toque 1:** botón grande "ENTRADA" en el home.
- **Toque 2:** la orden en la bandeja.
- **Toques 3..N+2:** "OK — llegó así" por cada producto (el saldo pendiente ya está precargado como default).
- **Toque final:** "validar partida".

Solo se tipea cuando la realidad difiere del saldo pendiente. Ahí el teclado numérico aparece con foco automático y el default editable.

## Home (sin cambios respecto de v0.2)

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
|   |     tanda)       |  |                  |  |  empacar)  | |
|   +------------------+  +------------------+  +------------+ |
|                                                              |
|                                          [ver mis registros] |
+--------------------------------------------------------------+
```

Los tres botones ocupan como mínimo 1/3 del alto útil. Color plano, texto en mayúsculas grandes. El "ver mis registros" es texto chico abajo — es la puerta a las correcciones posteriores.

Celular vertical (360x780 aprox): mismos tres botones apilados, cada uno ~1/4 del alto útil.

## Pantalla 1 — Bandeja de órdenes

Se abre después del toque 1. Solo muestra órdenes con trabajo pendiente: **abierta** (nunca llegó nada) y **recibida parcialmente** (algo llegó, falta el resto). Las cerradas y anuladas no aparecen acá.

```
+--------------------------------------------------------------+
|  <  ENTRADA — órdenes                                        |
+--------------------------------------------------------------+
|  +--------------------------------------------------------+  |
|  |  VERDULERIA NUÑEZ                       [ ABIERTA ]    |  |
|  |  hoy 14:00  ·  3 productos · todo pendiente            |  |
|  +--------------------------------------------------------+  |
|  +--------------------------------------------------------+  |
|  |  CARNICERIA LOPEZ              [ RECIBIDA PARCIAL ]    |  |
|  |  10 jul · 16:30  ·  faltan 40 kg POLLO                 |  |
|  +--------------------------------------------------------+  |
+--------------------------------------------------------------+
```

- **ABIERTA:** nunca llegó nada de esta orden. Badge oscuro, borde fuerte.
- **RECIBIDA PARCIAL:** llegó algo, falta el resto. Badge amarillo. El resumen muestra el saldo más significativo ("faltan 40 kg POLLO") en texto simple.
- Tocar una fila abre la verificación de la partida (Pantalla 2).
- Las órdenes cerradas y anuladas NO aparecen en esta bandeja. El dueño las ve en su panel de órdenes.

> PREGUNTA A BACKEND: si el operario abre una orden y abandona la pantalla sin validar, ¿el estado de la orden cambia? Asumo: no — la orden sigue en su estado (abierta o recibida parcial) hasta que se valide una partida. Lo que el operario confirmó en pantalla pero no validó se descarta al salir.

## Pantalla 2 — Verificación de la partida

La lista de ítems pendientes de la orden, con el **saldo pendiente** como default editable (no la cantidad original total). El primer ítem pendiente queda resaltado con foco.

```
+--------------------------------------------------------------+
|  <  ENTRADA — Carniceria Lopez    Partida #3                 |
+--------------------------------------------------------------+
|    CERDO      18 kg   (pedido: 20 kg · ya recibido: 2 kg)  ✓ |
|  ▶ POLLO      40 kg   (saldo pendiente)                      |
|              [ OK — llegó así ]  [ editar ]                  |
|                                                              |
|    CHARQUI    10 kg   (saldo pendiente)                      |
|                                                              |
|  al validar, esta partida impacta el stock                   |
|                              [ validar partida (1/3) ]       |
+--------------------------------------------------------------+
```

- **Default precargado:** saldo pendiente por producto (pedido original menos lo ya recibido en partidas anteriores).
- Debajo del default, en texto gris secundario: "(pedido: X · ya recibido: Y)" — referencia para el operario, no un análisis.
- **"OK — llegó así"** confirma que llegó exactamente el saldo pendiente en esta partida. Un toque.
- **"editar"** abre la pantalla de cantidad (Pantalla 3) con el saldo pendiente precargado.
- Los confirmados bajan a gris con tilde verde. Si se editó, muestra la cantidad recibida y el saldo entre paréntesis: quedan ambos valores.
- El botón "validar partida (1/3)" muestra el progreso y queda deshabilitado hasta confirmar todos los ítems.
- **Al validar, la partida impacta el stock.** Antes de eso, nada de lo confirmado afecta ningún número del sistema.
- **No se muestra ningún costo, precio ni total en soles.** Ni en los ítems, ni en el footer, ni en ningún lugar de esta pantalla.

> PREGUNTA A BACKEND: ¿el operario puede dejar un ítem en 0 ("no llegó nada de este producto en esta partida")? Asumo: sí — edita a 0, queda "anunciado vs. recibido = 0" para ese ítem en esta partida. El saldo pendiente del producto no cambia.

> PREGUNTA A BACKEND: ¿puede el operario registrar una cantidad mayor al saldo pendiente (exceso)? Asumo: sí, el sistema lo acepta y lo registra como discrepancia visible al dueño. El operario no ve aviso de discrepancia — solo ingresa lo que realmente llegó.

> PREGUNTA A BACKEND: ¿qué hace el operario si llegó un producto que NO está en la orden? Asumo: mismo comportamiento que v0.2 — no puede agregarlo. Le avisa al dueño por fuera.

## Pantalla 3 — Editar cantidad recibida en esta partida

Solo se abre cuando la realidad difiere del saldo pendiente. Default precargado (el saldo pendiente), foco automático, teclado numérico grande.

```
+--------------------------------------------------------------+
|  <  ENTRADA — POLLO  (saldo pendiente: 40 kg)                |
+--------------------------------------------------------------+
|                                                              |
|                 Cantidad recibida en esta partida            |
|                                                              |
|                 +----------------+                           |
|                 |      35        |   kg                      |
|                 +----------------+                           |
|                                                              |
|                 [ teclado numérico ]                         |
|                                                              |
|                 [    OK y siguiente  →    ]                  |
+--------------------------------------------------------------+
```

El saldo pendiente queda visible en el header como referencia — es el hecho a verificar, no un análisis. "OK y siguiente" guarda y salta al próximo ítem pendiente.

## Pantalla 4 — Partida validada (caso normal)

Confirmatorio de 1.5 segundos y vuelta a la bandeja:

```
+--------------------------------------------------------------+
|                                                              |
|                   [ tilde grande verde ]                     |
|                                                              |
|                   PARTIDA REGISTRADA                         |
|          Carniceria Lopez — partida #3 → stock actualizado   |
|                                                              |
|                        [   listo   ]                         |
|                                                              |
+--------------------------------------------------------------+
```

## Pantalla 4b — Partida validada cierra la orden (caso especial)

Si al validar la partida todos los ítems de la orden quedan con saldo 0, el cierre es automático. El operario solo ve:

```
+--------------------------------------------------------------+
|                                                              |
|                   [ tilde grande verde ]                     |
|                                                              |
|                   ORDEN COMPLETA                             |
|          Carniceria Lopez — todo llegó → stock actualizado   |
|                                                              |
|                        [   listo   ]                         |
|                                                              |
+--------------------------------------------------------------+
```

No hay paso extra. No hay decisión para el operario. El cierre es un evento automático append-only; el dueño lo ve en su panel como "cerrada".

## Estados

### Vacío (no hay órdenes abiertas ni con saldo pendiente)

```
+--------------------------------------------------------------+
|  <  ENTRADA — órdenes                                        |
+--------------------------------------------------------------+
|                                                              |
|            No hay órdenes con entregas pendientes.           |
|            Cuando el dueño cargue una, aparece acá.          |
|                                                              |
+--------------------------------------------------------------+
```

### Cargando

Skeletons con la forma de las filas de la bandeja. Nunca spinner centrado.

### Error (al validar la partida)

Toast rojo abajo, no bloqueante. Lo confirmado NO se pierde:

```
+--------------------------------------------------------------+
|  No se pudo registrar la partida. Tocá de nuevo.             |
+--------------------------------------------------------------+
```

### Sin conexión

Banner naranja arriba, no bloquea. Las confirmaciones se guardan local y se sincronizan al volver la red. El confirmatorio se muestra igual — el operario no espera al servidor.

```
+--------------------------------------------------------------+
|  Sin conexión — se guarda cuando vuelva                      |
+--------------------------------------------------------------+
```

> PREGUNTA A BACKEND: si dos dispositivos validan la misma orden offline simultáneamente (¿posible en un turno de cambio?), ¿qué pasa? Asumo: la primera en llegar al servidor gana; la segunda recibe un error con aviso claro.

## Correcciones

Un registro NUNCA se edita ni se borra. Corregir es crear un registro nuevo que apunta al anterior.

- **Antes de validar:** tocar un ítem ya confirmado permite re-confirmarlo o re-editarlo. Como la partida todavía no impactó stock, esto es parte de la verificación, no una corrección formal.
- **Después de validar:** desde "ver mis registros" del home (o desde la orden en la bandeja del dueño), el operario puede corregir la cantidad recibida de un producto en una partida ya validada. Eso crea un registro nuevo apuntando al original, y el stock se recalcula.

> PREGUNTA A BACKEND: ¿cuál es la ventana en la que el operario puede corregir una partida validada? Asumo: mismo día calendario Lima (hasta las 23:59 hora Lima del mismo día). Después, solo el dueño puede corregir.

## Qué NO se muestra nunca en este flujo

- Costo unitario, precio, total en soles. Nunca. Ni en la bandeja, ni al verificar, ni en el confirmatorio.
- Stock actual del producto.
- Totales, promedios, consumos.
- Cantidad total original de la orden (solo el saldo pendiente de esta partida).
- Historial de partidas anteriores de la misma orden (el operario ve el saldo resultante, no la historia).
- Discrepancias ni alertas de exceso (eso es del tablero del dueño).

La lista pre-cargada con su saldo pendiente **no** viola el principio de "no ver análisis": es el hecho declarado que el operario debe verificar en esta tanda, no un cálculo del sistema.
