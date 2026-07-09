# Registro de inventario (v0.2 — ex "cierre")

## Objetivo del flujo

Que el operario cuente cuánto queda de cada producto y lo anote. Un registro por producto. Sin ver lo que había, sin ver lo que llegó, sin ver lo que "debería" quedar.

## Cuándo se dispara

**El inventario NO está atado al turno.** Se cuenta:

- **Periódicamente**, con una frecuencia que define el dueño.
- **A pedido del dueño**, cuando quiere una foto fresca del stock (por ejemplo antes de una compra grande o ante una sospecha).

Cuando hay un conteo pendiente, el botón INVENTARIO del home lo indica (badge). Si no hay conteo pedido, el operario igual puede iniciar uno — nunca está de más un dato fresco.

> ⚠️ **ASUNCIÓN A CONFIRMAR CON EL DUEÑO:** la periodicidad concreta (¿semanal? ¿dos veces por semana? ¿sólo a pedido?) y cómo se le avisa al operario que hay un conteo pendiente (¿badge en el home alcanza?). El flujo de conteo en sí no depende de esta decisión.

## Usuario

Operario de turno. Está trabajando y el conteo compite con sus tareas — quiere terminarlo rápido. La pantalla no le muestra "lo esperado" a propósito: si viera un número esperado, "cuadraría" en vez de contar.

## Presupuesto

- **Camino feliz por producto:** 3 toques, menos de 5 segundos.
- **Toque 1:** botón "INVENTARIO" en el home.
- **Toque 2:** primer producto de la lista (aparece resaltado, foco automático).
- **Toque 3:** tipea cantidad + "SIGUIENTE" (o "OK" si es el último).

## Pantalla 1 — Lista de productos a contar

Se abre después de tocar "INVENTARIO" en el home. Lista vertical de todos los productos activos del catálogo, uno por fila, con el estado de cuenta al lado.

```
+--------------------------------------------------------------+
|  <  INVENTARIO — conteo del 8 de julio                       |
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
|                              [ terminar conteo  (2/10) ]     |
+--------------------------------------------------------------+
```

- Los productos pendientes están arriba, en negro fuerte, con "contar" en botón grande.
- Los ya contados bajan a gris con la cantidad que anotó (es su propio dato, no un dato del sistema).
- El botón "terminar conteo" muestra el progreso "(2/10)". No se puede terminar hasta contar todos, o hasta anotar "0" explícito en los faltantes.

> PREGUNTA A BACKEND: ¿el conteo exige contar TODOS los productos o puede ser parcial (el dueño pide contar sólo carnes, por ejemplo)? Asumo: completo en v0.2. Conteos parciales por categoría quedan para cuando existan categorías.

Celular vertical: mismo esquema, una fila por producto, se scrollea. Botón "terminar conteo" sticky abajo.

## Pantalla 2 — Contar producto

Foco automático en el campo, teclado numérico grande, sin sugerencia, sin "esperado", sin stock previo.

```
+--------------------------------------------------------------+
|  <  INVENTARIO — PALTA                                       |
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

## Pantalla 3 — Confirmación final del conteo

Cuando toca "terminar conteo" con todos contados:

```
+--------------------------------------------------------------+
|                                                              |
|                    [ tilde grande verde ]                    |
|                                                              |
|                   INVENTARIO REGISTRADO                      |
|                    10 productos contados                     |
|                                                              |
|                    [  corregir un producto  ]  [  listo  ]   |
|                                                              |
+--------------------------------------------------------------+
```

No se muestra la lista de cantidades. No se muestran totales ni diferencias con el conteo anterior. Sólo "listo".

## Estados

### Vacío (no hay productos en el catálogo)

```
+--------------------------------------------------------------+
|  <  INVENTARIO                                               |
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

### Éxito por producto

No hay pantalla intermedia. Vuelve directo a la lista con el producto ya en gris y "contado 4 unidades" al lado. La transición es la confirmación. Esto ahorra un toque por producto.

### Sin conexión

Banner naranja arriba, no bloqueante. Los conteos se guardan local y se sincronizan después.

## Correcciones

Un conteo NUNCA se sobreescribe. Aunque el operario toque "cambiar" en la lista, se crea un registro nuevo que apunta al anterior.

- **Durante el conteo:** botón "cambiar" al lado del producto ya contado. Abre la misma pantalla de contar con banner "CAMBIANDO — PALTA (antes: 4 unidades)". Es la única pantalla del flujo donde el operario ve un dato numérico previo — la referencia al hecho que corrige, no un total.
- **Después de terminar:** desde el confirmatorio final ("corregir un producto") o desde "ver mis registros" del home.

> PREGUNTA A BACKEND: ¿una vez terminado el conteo, cuánto tiempo puede el operario seguir corrigiendo? Asumo: mientras siga logueado ese día. Después, sólo el dueño.

## Qué NO se muestra nunca en este flujo

- Cuánto había en el conteo anterior.
- Cuánto llegó por entregas desde entonces.
- Cuánto "debería" quedar según lo pedido.
- Diferencia entre lo esperado y lo contado.
- Consumos, promedios, alertas.

Si el operario viera cualquiera de esos números, dejaría de contar y empezaría a cuadrar. El principio 1 lo prohíbe.
