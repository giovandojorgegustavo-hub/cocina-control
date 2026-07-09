# Requerimientos v0.1 — Cocina Control

Sistema para que el dueño de una dark kitchen detecte fugas de inventario sin cambiarle la vida al operario. En v0.1 sólo capturamos hechos crudos (qué llegó, qué queda, qué se pidió) y mostramos consumo por diferencia. La caza de fugas por receta queda para más adelante.

## Contexto

- **Negocio:** dark kitchen con 4 operarios part-time. Un operario por turno, cada uno trabaja 3 o 4 días por semana.
- **Problema:** el dueño sospecha fugas de inventario. El control es manual: llega una hoja con las compras, se confía que vino completo, al cierre se cuenta lo que queda, y el dueño calcula consumos a mano restando inventarios.
- **Objetivo v0.1:** reemplazar la hoja de papel por un registro digital confiable y darle al dueño un tablero para ver consumo, stock y alertas. Sin fricción para el operario.

## Alcance v0.1

Tres registros de eventos y un tablero de lectura.

| Registro | Cuándo se usa | Qué se anota |
|---|---|---|
| **Entrada** | Llegó una compra | Cuánto llegó de cada producto |
| **Cierre** | Fin del turno | Cuánto queda de cada producto |
| **Pedido** | Entró un pedido (Rappi / PedidosYa) | Que entró un pedido |

**Tablero del dueño** (sólo lectura, sólo dueño):

- Consumo por diferencia: `inventario anterior + entradas − inventario actual`
- Stock actual por producto
- Productos por acabarse

Los productos se manejan como items independientes. Sin recetas, sin platos compuestos en v0.1.

## Principios de diseño (no negociables)

Estas reglas mandan sobre cualquier decisión de implementación. Si algo las contradice, gana el principio.

### 1. El operario sólo cuenta y anota

Nunca ve análisis, totales, promedios, ni lo que el sistema "espera" que haya. Su pantalla muestra el campo para anotar y nada más. Ver totales invita a "cuadrar" el número en vez de contar la realidad.

### 2. Registrar un evento toma menos de 5 segundos

Tablet o celular, con las manos ocupadas o sucias. Botones grandes, mínimos toques, respuesta instantánea. Si un registro requiere más de 5 segundos o más de 3 toques, hay que rediseñar el flujo.

### 3. Nada se borra ni se edita sin rastro

Los usuarios son también potenciales auditados. Toda corrección es un **registro nuevo** que corrige uno anterior, nunca sobreescritura. Cada registro guarda quién, qué, cuándo, y — si corrige — a qué registro previo apunta.

### 4. Productos como items independientes

Sin recetas, sin BOM, sin componentes. Cada producto se cuenta como una unidad atómica en v0.1. Esto se rompe deliberadamente en una versión futura (ver más abajo).

## Fuera de alcance v0.1

Cada uno de estos ítems se convierte en un issue de GitHub cuando sea el momento. **No** entran a v0.1.

- **Recetas por plato.** Cruzar consumo esperado (ej: guacamole = 1 palta + 20g yogurt) contra consumo real medido. Es el detector de fugas real. Requiere que v0.1 esté estable y con datos limpios primero.
- **Integración automática con Rappi / PedidosYa.** En v0.1 el operario anota el pedido a mano. Después se conectan las APIs.
- **Múltiples cocinas.** El modelo de datos no debe cerrar la puerta a esto, pero la UI y la lógica de v0.1 asumen una sola cocina.

## Criterios de aceptación de v0.1

Sirve para saber cuándo v0.1 está terminada.

- [ ] Un operario puede registrar una **entrada** en menos de 5 segundos desde que abre la app.
- [ ] Un operario puede registrar un **cierre** en menos de 5 segundos por producto.
- [ ] Un operario puede registrar un **pedido** en menos de 5 segundos.
- [ ] El operario nunca ve totales, consumos, ni comparativas.
- [ ] Toda corrección queda como un registro nuevo con referencia al original; el registro original no se modifica.
- [ ] El dueño ve, en su tablero, consumo por diferencia, stock actual y productos por acabarse — de un solo vistazo.
- [ ] El dueño puede reconstruir la trazabilidad completa de cualquier producto (todos los eventos que lo tocaron).

## Próximos pasos

1. UX define wireframes de las tres pantallas del operario y del tablero del dueño.
2. Backend define modelo de datos append-only para los tres registros.
3. Frontend implementa los flujos siguiendo las especificaciones de UX.
