# Registro de pedido

## Objetivo del flujo

Que el operario avise, con un toque, que entró un pedido de Rappi o PedidosYa. No importa qué se pidió — importa el hecho de que entró. Es el registro más simple de los tres.

## Usuario

Operario en pleno servicio. Suena el timbre del pedido, tiene que empezar a preparar. Cada segundo cuenta más que en entrada o cierre.

## Presupuesto

- **Camino feliz:** 2 toques, menos de 3 segundos.
- **Toque 1:** botón "PEDIDO" en el home.
- **Toque 2:** elige plataforma (Rappi / PedidosYa / otro).

No hay teclado, no hay lista de productos, no hay cantidad. Sólo dos tarjetas grandes.

## Pantalla 1 — Elegir plataforma

Se abre después del toque 1. Dos (o tres) tarjetas gigantes, del alto máximo posible, con el logo o inicial de la plataforma. Cada tarjeta ocupa la mitad del ancho útil.

Tablet horizontal:

```
+--------------------------------------------------------------+
|  <  PEDIDO — ¿de dónde?                                      |
+--------------------------------------------------------------+
|                                                              |
|   +---------------------+   +---------------------+          |
|   |                     |   |                     |          |
|   |                     |   |                     |          |
|   |       RAPPI         |   |     PEDIDOSYA       |          |
|   |                     |   |                     |          |
|   |                     |   |                     |          |
|   +---------------------+   +---------------------+          |
|                                                              |
|                       [   otro    ]                          |
+--------------------------------------------------------------+
```

Celular vertical: mismas dos tarjetas, apiladas una arriba de la otra, cada una ocupando ~35% del alto útil. "Otro" queda como link chico abajo.

```
+----------------------+
|  <  PEDIDO           |
+----------------------+
|                      |
| +------------------+ |
| |                  | |
| |      RAPPI       | |
| |                  | |
| +------------------+ |
|                      |
| +------------------+ |
| |                  | |
| |    PEDIDOSYA     | |
| |                  | |
| +------------------+ |
|                      |
|     [   otro    ]    |
+----------------------+
```

> PREGUNTA A BACKEND: ¿el catálogo de plataformas es fijo (Rappi, PedidosYa, otro) o el dueño puede agregar más (ej. Uber Eats)? Asumo: catálogo fijo para v0.1, con "otro" como escape. En v0.2 lo hace configurable.

## Pantalla 2 — Confirmación

Instantánea, 1.5 segundos, y vuelve al home:

```
+--------------------------------------------------------------+
|                                                              |
|                   [ tilde grande verde ]                     |
|                                                              |
|                    PEDIDO REGISTRADO                         |
|                    Rappi — 20:42                             |
|                                                              |
|                   [  corregir  ]   [   listo   ]             |
|                                                              |
+--------------------------------------------------------------+
```

"Corregir" queda visible sólo durante los 1.5s del confirmatorio, y también desde "mis registros" del home.

## Qué se registra en el modelo

- Plataforma (Rappi / PedidosYa / otro).
- Timestamp exacto del toque 2.
- Operario del turno.

No se registra qué productos se pidieron. Eso llega cuando se integren las APIs (fuera de alcance v0.1).

> PREGUNTA A BACKEND: ¿el registro de pedido necesita un contador (ej. "3 pedidos de Rappi en la última hora") o cada toque es un evento independiente sin agregación previa? Asumo: cada toque es un evento independiente. La agregación la hace el tablero del dueño.

## Estados

### Vacío

No aplica — siempre hay al menos "Rappi", "PedidosYa" y "otro".

### Cargando

Skeletons de dos tarjetas grises. En la práctica, esta pantalla debería cargar instantánea porque el catálogo de plataformas es fijo y cabe en el bundle.

### Error (al guardar)

Toast rojo abajo, no bloqueante:

```
+--------------------------------------------------------------+
|  No se pudo guardar. Tocá de nuevo.                          |
+--------------------------------------------------------------+
```

Las tarjetas siguen tocables. Se puede reintentar sin perder nada.

### Éxito

Ya descripto arriba: confirmatorio de 1.5s con "corregir" y "listo".

### Sin conexión

Banner naranja arriba, no bloquea:

```
+--------------------------------------------------------------+
|  Sin conexión — se guarda cuando vuelva                      |
+--------------------------------------------------------------+
|  <  PEDIDO — ¿de dónde?                                      |
| ...                                                          |
```

El toque en la tarjeta se guarda local, se confirma al operario y se sincroniza cuando vuelve la red. Este es CRÍTICO acá: el operario no puede quedarse esperando servidor cuando está entrando el pedido.

## Correcciones

Un pedido registrado por error también se corrige como registro nuevo, nunca borrado.

### Caso típico

El operario tocó "Rappi" cuando era "PedidosYa". O tocó "PEDIDO" sin querer (falso positivo).

### Pantalla de corrección

Desde el confirmatorio o desde "mis registros", tocar "corregir" abre:

```
+--------------------------------------------------------------+
|  <  CORRIGIENDO — Pedido de 20:42 (antes: Rappi)             |
+--------------------------------------------------------------+
|                                                              |
|   +---------------------+   +---------------------+          |
|   |       RAPPI         |   |     PEDIDOSYA       |          |
|   +---------------------+   +---------------------+          |
|                                                              |
|                       [  otro  ]                             |
|                                                              |
|                       [  anular  ]                           |
+--------------------------------------------------------------+
```

- Tocar otra plataforma: crea registro nuevo apuntando al original, con la plataforma correcta.
- Tocar "anular": crea registro nuevo apuntando al original, marcado como "anulado" (falso positivo).

En ambos casos, el registro original queda intacto en el modelo. El tablero del dueño puede mostrar la corrección o el estado final según necesite.

> PREGUNTA A BACKEND: ¿existe el concepto de "registro anulado" en el modelo, o toda corrección es un cambio de dato (nunca una anulación pura)? Si no existe, el flujo de "anular" queda pendiente hasta que backend lo defina.

## Qué NO se muestra nunca en este flujo

- Cuántos pedidos van hoy.
- Cuántos pedidos van del turno.
- Ranking de plataformas.
- Ninguna estadística agregada.

Ese análisis es del dueño, no del operario.
