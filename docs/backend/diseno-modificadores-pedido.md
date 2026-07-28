# Diseño — Modificadores en la captura de pedidos

Estado: **propuesta**, sin implementar. Escrito antes de la migración a pedido del dueño.

## El problema

Hoy un pedido registra `producto × cantidad`. Eso alcanza para un Bowl crispy, cuya
composición está publicada en la carta y el sistema puede dar por conocida. No alcanza
para **Arma tu bowl**: dos bases de tres, cinco a siete toppings de dieciocho, proteína,
garnish y salsa, todo elegido por el cliente. Sin capturar esa elección, el consumo
teórico de ese producto es una invención, y la fuga que se calcule contra él, ruido.

Tampoco alcanza para los extras de un armado: la proteína adicional, la crema y su
tamaño, y la bebida. Son consumo real que hoy no queda registrado en ningún lado.

## Principio rector

**Se captura lo que varía. Lo que está en la carta, el sistema ya lo sabe.**

De ahí sale la asimetría que estructura todo el diseño:

| | Qué varía | Qué abre |
|---|---|---|
| Bowl / wrap armado | proteína extra, crema + tamaño, bebida | Hoja chica, todo en "ninguna" por defecto |
| Arma tu bowl / wrap | todo | Hoja completa: bases, toppings, proteína, garnish, salsa, bebida |

El caso normal — un armado sin extras — se registra con **un toque**. El costo del modal
se paga solo donde el dato lo exige. Esto es lo que preserva la restricción de
`.claude/contexto-producto.md`: *menos de 5 segundos y menos de 3 toques*.

### Por qué esto no viola "el operario nunca ve recetas"

La restricción #3 prohíbe exponerle al operario las **recetas**: la estimación en gramos
que hace el dueño para calcular consumo teórico, más los factores de conversión y las
equivalencias. Nada de eso aparece acá.

Lo que el operario ve es el **menú**: las opciones que el cliente eligió al comprar. Es
información que el operario ya tiene en el ticket, en el mismo vocabulario del cliente y
sin una sola cantidad. Son dos objetos distintos y solo uno cruza a la pantalla de captura.

### Cubiertos quedan afuera

`docs/requerimientos.md` dice que el packing —bowl, tapa, cubiertos, bolsa— **se consume
por pedido** y ya entra en la receta del plato. Preguntarlo otra vez en la hoja lo
contaría dos veces. Decisión del dueño (28 jul 2026): fuera.

## Modelo de datos

Migración `0017_product_option_groups`.

Los grupos son **reutilizables**: "Proteína extra" se define una vez y se engancha a los
seis bowls y los cuatro wraps. Duplicarlo por producto sería diez copias que se
desincronizan al primer cambio de carta.

```
option_groups            un grupo de opciones, reutilizable
  id, name, min_select, max_select, is_active, created_by, created_at

option_group_items       las opciones dentro del grupo
  id, option_group_id FK, name, position,
  linked_product_id FK products NULL,
  is_active, created_by, created_at

product_option_groups    qué grupos abre cada producto (join)
  product_id FK, option_group_id FK, position
  PK (product_id, option_group_id)

delivery_order_item_options   qué se eligió en cada línea del pedido
  id, delivery_order_item_id FK, option_group_item_id FK,
  created_by, created_at, corrects_id FK self NULL
```

Notas de forma:

- **Sin cantidad por opción.** "Selecciona hasta 2 opciones" significa dos opciones
  distintas, no dos veces la misma. Cada elección vale 1. Si algún día hace falta, se
  agrega la columna; hoy sería complejidad sin caso de uso.
- **`linked_product_id`** es cómo la elección se traduce en consumo: la opción
  "Pollo deshilachado" apunta al producto `POLLO DESHILACHADO`, y la receta de ese
  producto —que sigue siendo del dueño y solo del dueño— dice cuántos gramos. Es
  nullable: "Sin proteína" no consume nada.
- **`corrects_id`** en las opciones elegidas, igual que en `delivery_order_items`.
  Corregir un pedido escribe filas nuevas, nunca pisa las viejas.
- **Todo append-only.** Cambiar la carta desactiva opciones (`is_active = false`), no las
  borra: un pedido de marzo tiene que seguir siendo reconstruible con las opciones que
  existían en marzo.

### El tamaño de la crema

Entre 2 oz y 4 oz hay el doble de consumo, así que el tamaño **no puede quedar
implícito**. Se modela como un grupo propio, `Tamaño de crema`, con dos opciones.

Alternativa descartada: duplicar cada crema en dos productos (`VINAGRETA 2 OZ`,
`VINAGRETA 4 OZ`). Dobla el catálogo, obliga al operario a distinguir diez tarjetas casi
idénticas en una pantalla de cocina, y mezcla dos ejes —qué crema y cuánta— en una sola
dimensión.

> **Deuda inmediata:** las 5 cremas ya cargadas en producción (28 jul 2026) no declaran
> tamaño. Hasta que este diseño se implemente, su consumo teórico es ambiguo por un
> factor de dos.

## Grupos a cargar

Relevados del menú de Bonabowl - Orbea en Rappi.

**Para los armados** (6 bowls, 4 wraps): `Proteína extra`, `Crema`, `Tamaño de crema`,
`Bebida`. Todos con `min_select = 0`.

**Para Arma tu bowl**: `Bases` (2 de 3), `Toppings` (5 a 7), `Proteína` (hasta 2),
`Garnish` (1), `Salsa` (1), `Bebida` (hasta 3).

**Para Arma tu wrap**: igual, con `Bases` (1 de 3) y `Toppings` (4 a 6).

Los precios de Rappi (+$3, +$8) no se transcriben: el catálogo no tiene precios y el
operario no ve plata en ninguna ruta.

## API

`GET /products?flow=sale` devuelve los grupos y opciones **anidados**, no por endpoint
aparte. La app es una PWA que corre en una cocina con wifi irregular: una sola respuesta
cacheable permite abrir la hoja sin red. Un `GET` por producto al tocar cada fila sería
un round-trip en el peor momento posible.

`POST /delivery-orders/{id}/complete` y `/correct` aceptan opciones por línea:

```json
{"items": [{"product_id": "…", "quantity": 1, "option_item_ids": ["…", "…"]}]}
```

Validaciones en el backend, no solo en la UI: cada `option_item_id` pertenece a un grupo
enganchado a ese producto, y la cantidad de elecciones por grupo respeta `min_select` y
`max_select`. La UI puede mentir; el backend no.

## Pantalla

Una columna, 100% celular, operario con las manos sucias.

- Filas de **56 px**, toda la fila tocable. Bowls y wraps arriba, sueltos abajo.
- **Tocar la fila registra el producto** con los grupos en su valor por defecto. Un toque.
- Debajo de una fila ya registrada aparece una tira fina *extras* que abre la hoja. Opt-in.
- **Hoja inferior**, no diálogo centrado: en un celular sostenido con una mano, el centro
  de la pantalla es la zona a la que el pulgar no llega. Chips de 44 px, botón grande abajo.
- Los armables abren la hoja completa siempre — ahí no hay default posible.

## Anular y corregir

El backend ya lo tiene: `POST /delivery-orders/{id}/cancel` y `/correct`, ambos
append-only vía `corrects_id`. Faltan las pantallas (issues #70 y #71).

Para el operario se va a sentir como borrar en cualquier app. Por debajo **no se borra
nada**: se escribe un registro nuevo con motivo que apunta al anterior. Si el operario
pudiera borrar de verdad un pedido mal cargado, podría borrar también uno bien cargado —
y el detector de fugas tendría un agujero exactamente donde a alguien le conviene.

## Alcance

En este diseño: modelo, carga de grupos, API con validación, pantalla de captura, anular
y corregir.

Fuera: recetas de las opciones (`linked_product_id` queda listo, el cálculo teórico es
otro trabajo), precios, y edición de la carta desde la UI — los grupos se cargan por
script hasta que exista la pantalla de catálogo (issue #125).
