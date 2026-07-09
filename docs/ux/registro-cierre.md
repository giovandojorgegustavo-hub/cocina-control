# Registro de cierre

## Objetivo del flujo

Que el operario cuente, al final del turno, cuánto queda de cada producto y lo anote. Un registro por producto. Sin ver lo que había, sin ver lo que llegó, sin ver lo que "debería" quedar.

## Usuario

Operario de turno, al cierre. Está apurado — quiere irse. La pantalla no le muestra "lo esperado" a propósito: si viera un número esperado, "cuadraría" en vez de contar.

## Presupuesto

- **Camino feliz por producto:** 3 toques, menos de 5 segundos.
- **Toque 1:** botón "CIERRE" en el home.
- **Toque 2:** primer producto de la lista de cierre (aparece resaltado, foco automático).
- **Toque 3:** tipea cantidad + "SIGUIENTE" (o "OK" si es el último).

El requerimiento oficial dice "menos de 5 segundos por producto". Cumple.

## Pantalla 1 — Lista de productos a contar

Se abre después de tocar "CIERRE" en el home. Lista vertical de todos los productos activos del catálogo, uno por fila, con el estado de cuenta al lado.

Tablet horizontal:

```
+--------------------------------------------------------------+
|  <  CIERRE — turno de Juan, 22:30                            |
+--------------------------------------------------------------+
|                                                              |
|  > PALTA                              [ contar ]             |
|                                                              |
|    POLLO                              [ contar ]             |
|                                                              |
|    TOMATE                             [ contar ]             |
|                                                              |
|    CEBOLLA           contado 3 kg     [ cambiar ]            |
|                                                              |
|    QUESO             contado 1,5 kg   [ cambiar ]            |
|                                                              |
|    ...                                                       |
|                                                              |
|                              [ terminar cierre  (2/10) ]     |
+--------------------------------------------------------------+
```

- Los productos pendientes están arriba, en negro fuerte, con "contar" en botón grande.
- Los ya contados bajan a gris con la cantidad que anotó (esto es su propio dato, no un dato del sistema).
- El botón "terminar cierre" en el pie muestra el progreso "(2/10)". No se puede terminar hasta contar todos, o hasta marcar los faltantes como cero.

> PREGUNTA A BACKEND: ¿el cierre exige contar TODOS los productos o el operario puede saltear alguno? Asumo: exige todos. Un producto no contado bloquea el cierre. Puede anotarse "0" explícitamente.

Celular vertical: mismo esquema, una fila por producto, se scrollea. Botón "terminar cierre" sticky abajo.

```
+----------------------+
| <  CIERRE   22:30    |
+----------------------+
| > PALTA              |
|     [   contar   ]   |
+----------------------+
|   POLLO              |
|     [   contar   ]   |
+----------------------+
|   TOMATE             |
|     [   contar   ]   |
+----------------------+
|   CEBOLLA            |
|   contado 3 kg       |
|     [  cambiar  ]    |
+----------------------+
| [ terminar (2/10) ]  |
+----------------------+
```

## Pantalla 2 — Contar producto

Igual que la pantalla de cantidad de entrada, pero con la palabra CIERRE arriba. Foco automático en el campo, teclado numérico grande, sin sugerencia, sin "esperado", sin stock previo.

```
+--------------------------------------------------------------+
|  <  CIERRE — PALTA                                           |
+--------------------------------------------------------------+
|                                                              |
|                 Cantidad que queda                           |
|                                                              |
|                 +----------------+                           |
|                 |       4        |   unidades                |
|                 +----------------+                           |
|                                                              |
|                 [ teclado numérico ]                         |
|                                                              |
|             [  SIGUIENTE  →  ]   [   OK y volver  ]          |
+--------------------------------------------------------------+
```

- **SIGUIENTE →** guarda el registro del producto actual y salta al próximo pendiente. Es el botón por defecto y el más grande.
- **OK y volver** guarda y vuelve a la lista. Útil si el operario quiere cambiar el orden.

## Pantalla 3 — Confirmación final del cierre

Cuando toca "terminar cierre" con todos contados:

```
+--------------------------------------------------------------+
|                                                              |
|                    [ tilde grande verde ]                    |
|                                                              |
|                    CIERRE REGISTRADO                         |
|                    10 productos contados                     |
|                                                              |
|                    [  corregir un producto  ]  [  listo  ]   |
|                                                              |
+--------------------------------------------------------------+
```

No se muestra la lista de cantidades. No se muestran totales ni diferencias con la apertura. Sólo "listo".

## Estados

### Vacío (no hay productos en el catálogo)

```
+--------------------------------------------------------------+
|  <  CIERRE                                                   |
+--------------------------------------------------------------+
|                                                              |
|            No hay productos cargados.                        |
|            Pedile al dueño que los cargue.                   |
|                                                              |
+--------------------------------------------------------------+
```

### Cargando

Skeletons grises con la misma forma de la lista. Nunca spinner solo.

### Error (al guardar un producto)

Toast rojo abajo, no bloqueante. El botón SIGUIENTE queda activo. La cantidad tipeada NO se pierde.

```
+--------------------------------------------------------------+
|  No se pudo guardar. Tocá SIGUIENTE de nuevo.                |
+--------------------------------------------------------------+
```

### Éxito por producto

No hay pantalla intermedia. Vuelve directo a la lista con el producto ya en gris y "contado 4 unidades" al lado. La transición es la confirmación. Esto ahorra un toque por producto.

### Sin conexión

Banner naranja arriba, no bloqueante:

```
+--------------------------------------------------------------+
|  Sin conexión — se guarda cuando vuelva                      |
+--------------------------------------------------------------+
|  <  CIERRE — turno de Juan, 22:30                            |
| ...                                                          |
```

Los conteos se guardan local y se sincronizan después. El operario cierra su turno sin esperar.

## Correcciones

Un conteo NUNCA se sobreescribe. Aunque el operario toque "cambiar" en la lista, se crea un registro nuevo que apunta al anterior.

### Durante el cierre (antes de "terminar cierre")

Botón "cambiar" al lado del producto ya contado. Abre la misma pantalla de contar, con banner:

```
+--------------------------------------------------------------+
|  <  CAMBIANDO — PALTA (antes: 4 unidades)                    |
+--------------------------------------------------------------+
|                                                              |
|                 Nueva cantidad                               |
|                 +----------------+                           |
|                 |       5        |   unidades                |
|                 +----------------+                           |
|                                                              |
|                 [ teclado numérico ]                         |
|                                                              |
|                 [       OK        ]                          |
+--------------------------------------------------------------+
```

Al confirmar, se crea un registro nuevo que apunta al anterior. El anterior queda en el modelo, no se muestra más en la lista.

Como en entrada, esta es la única pantalla donde el operario ve un dato numérico previo — es la referencia al hecho que corrige, no un total ni un consumo.

### Después de terminar cierre

Desde el confirmatorio final: botón "corregir un producto" que abre la lista de productos ya contados con "cambiar" al lado de cada uno.

Desde el home más tarde: "ver mis registros" del turno actual muestra todos los conteos con opción "cambiar" (mismo criterio que el flujo de entrada).

> PREGUNTA A BACKEND: ¿una vez que el operario tocó "terminar cierre" y cerró su turno, puede seguir corrigiendo esos conteos? Asumo: sí, mientras siga logueado en el turno. Cuando cambia de turno o pasa cierta ventana (definir), sólo el dueño puede corregir.

## Qué NO se muestra nunca en este flujo

- Cuánto había al abrir el turno.
- Cuánto llegó por entradas durante el turno.
- Cuánto "debería" quedar según lo pedido.
- Diferencia entre lo esperado y lo contado.
- Consumos, promedios, alertas.

Si el operario viera cualquiera de esos números, dejaría de contar y empezaría a cuadrar. El principio 1 lo prohíbe.
