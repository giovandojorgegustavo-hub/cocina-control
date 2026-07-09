# Registro de pedido (v0.2 — foto primero, no bloqueante)

## Objetivo del flujo

Que el operario capture, con una foto al momento de empacar, qué salió físicamente de la cocina. La foto es el registro primario y toma segundos. El detalle de productos se completa después, cuando el servicio afloja — o no se completa nunca, y la foto vale igual como evidencia.

## Usuario

Operario en pleno servicio. Está empacando el pedido para despachar. Cada segundo cuenta más que en cualquier otro flujo: **nada puede bloquear el despacho**.

## Presupuesto

- **Foto (camino crítico):** 2 toques, menos de 5 segundos, no bloqueante.
- **Toque 1:** botón "PEDIDO" en el home.
- **Toque 2:** disparador de la cámara.
- **Completar (diferido):** sin presupuesto estricto — se hace cuando el operario puede. Elegir productos son toques sobre tarjetas grandes, sin teclado.

## Pantalla 1 — Foto al empacar

Se abre después del toque 1, directo en la cámara. Sin pasos previos.

```
+--------------------------------------------------------------+
|  <  PEDIDO — sacale foto al paquete                          |
+--------------------------------------------------------------+
|  +--------------------------------------------------------+  |
|  |                                                        |  |
|  |                   [ vista de cámara ]                  |  |
|  |                   encuadrá el paquete                  |  |
|  |                                                        |  |
|  +--------------------------------------------------------+  |
|                                                              |
|                        ( disparador )                        |
|                                                              |
|     sacá la foto y seguí — el detalle se completa después    |
+--------------------------------------------------------------+
```

- El disparador es el único control. Sacar la foto guarda el registro y muestra el confirmatorio.
- No hay selección de plataforma, ni lista de productos, ni ningún paso más. La foto ES el registro.

> PREGUNTA A BACKEND: ¿registramos la plataforma (Rappi / PedidosYa) en algún momento del flujo? v0.2 la saca del camino crítico y no la pide tampoco al completar. Si el dueño la necesita para su análisis, se agrega como toque opcional en "completar" — confirmar con el dueño.

## Pantalla 2 — Guardado (pendiente)

Confirmatorio de 1.5 segundos y vuelta al home:

```
+--------------------------------------------------------------+
|                                                              |
|                   [ tilde grande verde ]                     |
|                                                              |
|                    PEDIDO GUARDADO                           |
|     20:42 — queda PENDIENTE en la bandeja,                   |
|              completalo cuando puedas                        |
|                                                              |
|                        [   listo   ]                         |
|                                                              |
+--------------------------------------------------------------+
```

## Pantalla 3 — Bandeja de pedidos

Accesible desde el home (mismo botón "PEDIDO" muestra la bandeja abajo de la cámara, o "ver mis registros"). Más nuevos arriba.

```
+--------------------------------------------------------------+
|  <  PEDIDOS — bandeja                                        |
+--------------------------------------------------------------+
|  +--------------------------------------------------------+  |
|  | [foto]  20:42 · hoy         [ PENDIENTE ] [completar] |  |
|  |         sin detalle todavía                            |  |
|  +--------------------------------------------------------+  |
|  +--------------------------------------------------------+  |
|  | [foto]  19:15 · hoy  (gris)      [ TERMINADO ✓ ]      |  |
|  |         3 productos                                    |  |
|  +--------------------------------------------------------+  |
|  +--------------------------------------------------------+  |
|  | [foto]  21:03 · ayer        [ PENDIENTE ] [completar] |  |
|  |         solo foto                                      |  |
|  +--------------------------------------------------------+  |
+--------------------------------------------------------------+
```

- **Estados: pendiente → terminado.** El badge PENDIENTE lleva borde amarillo; TERMINADO baja a gris con tilde.
- Un pendiente viejo ("solo foto") no molesta ni bloquea nada: puede quedar así indefinidamente y el tablero del dueño lo muestra como pedido sin detalle.
- La miniatura de la foto identifica el pedido — es más rápido reconocer el paquete que leer una hora.

## Pantalla 4 — Completar pedido

Se abre al tocar "completar" en un pendiente.

```
+--------------------------------------------------------------+
|  <  COMPLETAR — pedido de 20:42                              |
+--------------------------------------------------------------+
|  +----------------+   ¿qué salió en este pedido? (mínimo 1)  |
|  |                |                                          |
|  |    foto del    |   +----------+ +----------+ +--------+   |
|  |    paquete     |   | PALTA ×2 | | POLLO ×1 | | TOMATE |   |
|  |                |   +----------+ +----------+ +--------+   |
|  |                |   +----------+ +----------+ +--------+   |
|  |                |   |  QUESO   | |   PAN    | | ARROZ  |   |
|  +----------------+   +----------+ +----------+ +--------+   |
|                                                              |
|  dejar solo foto por ahora    [ terminar pedido (2 productos)]|
+--------------------------------------------------------------+
```

- La foto queda a la vista mientras se eligen los productos — el operario mira el paquete, no recuerda de memoria.
- Tocar una tarjeta la selecciona con cantidad ×1; tocarla de nuevo suma. Las seleccionadas se pintan oscuras con la cantidad.
- **"terminar pedido" exige mínimo 1 producto.** Con cero seleccionados, el botón queda deshabilitado.
- **"dejar solo foto por ahora"** vuelve a la bandeja sin cambiar el estado: sigue pendiente.

> PREGUNTA A BACKEND: ¿un operario puede completar un pedido que fotografió otro operario (turno anterior)? Asumo: sí — el registro guarda quién sacó la foto y quién completó el detalle, como eventos separados.

## Pantalla 5 — Terminado

Confirmatorio de 1.5 segundos y vuelta a la bandeja:

```
+--------------------------------------------------------------+
|                                                              |
|                   [ tilde grande verde ]                     |
|                                                              |
|                   PEDIDO TERMINADO                           |
|                pedido de 20:42 — 2 productos                 |
|                                                              |
|                        [   listo   ]                         |
|                                                              |
+--------------------------------------------------------------+
```

## Qué se registra en el modelo

- **Al sacar la foto:** la foto, timestamp exacto, operario. Estado: pendiente.
- **Al completar:** lista de productos con cantidades (mínimo 1), operario que completó, timestamp. Estado: terminado.
- Ambos son eventos separados en el modelo append-only: la foto nunca se toca al completar.

## Estados

### Vacío (bandeja sin pedidos)

"Todavía no hay pedidos hoy. Sacá la primera foto al empacar."

### Cargando

Skeletons con la forma de las filas (miniatura + dos líneas). Nunca spinner solo.

### Error (al subir la foto)

La foto queda en cola local y se reintenta sola. El operario ve el confirmatorio igual — el pedido aparece en la bandeja con la miniatura local. No hay toast: no hay nada que el operario deba hacer.

### Sin conexión

**Crítico acá.** Banner naranja, no bloquea nada: la foto se guarda local, el confirmatorio sale igual, y la cola sube cuando vuelve la red. El operario jamás espera al servidor con un pedido en la mano.

```
+--------------------------------------------------------------+
|  Sin conexión — la foto se sube cuando vuelva                |
+--------------------------------------------------------------+
```

> PREGUNTA A BACKEND: ¿cuánto pesa la foto y cuánto se retiene? Asumo: se comprime en el dispositivo (~500KB) y se retiene mínimo 90 días. Confirmar política de retención con el dueño.

## Correcciones

Un pedido NUNCA se borra. Todo se corrige con registros nuevos:

- **Foto por error (falso positivo):** desde la bandeja, el pedido pendiente ofrece "anular" — crea un registro nuevo que marca el original como anulado. La foto queda.
- **Detalle mal completado:** un pedido terminado ofrece "corregir productos" — crea un registro nuevo con la lista corregida apuntando al anterior.

## Qué NO se muestra nunca en este flujo

- Cuántos pedidos van hoy / del período.
- Ranking de productos ni de nada.
- Ninguna estadística agregada.

Ese análisis es del dueño, no del operario. La bandeja muestra sólo lo operativo: qué está pendiente de completar.
