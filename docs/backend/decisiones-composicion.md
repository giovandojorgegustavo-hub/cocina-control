# Decisiones — composición de platos

## El problema

El catálogo tiene dos islas y ningún puente. Por un lado los insumos que entran
por órdenes de compra (`is_purchase`). Por el otro los platos que salen en
pedidos (`is_sale`). Ninguna fila dice qué se lleva un `FOCUS BOWL`.

La consecuencia: vender 12 focus bowl no permite deducir cuánta tilapia salió.
El detector de fuga —restar consumo esperado contra inventario real— no puede
existir mientras falte ese puente. Se cuenta el inventario el sábado, falta
tilapia, y nadie puede distinguir venta de merma.

## Dos tablas, no una

Bonabowl vende dos clases de plato y sólo una tiene receta declarable.

**`product_recipe`** — la plantilla del plato fijo (`FOCUS BOWL`, `WRAP FRESH`).
La receta es constante: se declara una vez y se multiplica por lo vendido.

**`delivery_order_item_ingredients`** — lo que llevó una línea de pedido concreta.
Para los armables (`ARMA TU BOWL`, `ARMA TU SALAD`) el cliente compone el plato
en el momento; no hay plantilla que declarar y la única verdad es el ticket de
ese pedido.

Aplica a las dos clases: un `FOCUS BOWL` también trae salsa y cubiertos
elegidos por el cliente, y eso vive acá, no en la receta.

## `quantity` es NULL-able a propósito

Hoy nadie en la cocina sabe los gramos. Inventarlos produciría un consumo
esperado falso que después nadie vuelve a cuestionar — y un número equivocado
con cara de dato es peor que ningún número.

Primero se captura **qué** lleva cada plato. Las cantidades se completan cuando
el registro acumulado las haga evidentes. Un ingrediente sin cantidad ya sirve
para contar frecuencia y para saber qué insumo toca qué plato.

Por eso `quantity = 0` está prohibido por CHECK: `NULL` significa "todavía no
medido", cero significaría "medido, y es nada". No son lo mismo.

## `status` y el quiebre de stock

Un bowl servido sin palta porque se acabó es indistinguible de un bowl que
nunca la llevaba, salvo que quede la marca. `out_of_stock` la deja.

Es la única señal temprana de quiebre que la cocina genera sin trabajo extra:
el operario ya está registrando el pedido, marcar "no había" cuesta un toque.

Un ingrediente `out_of_stock` no puede llevar cantidad (CHECK). Lo que no salió
no consumió nada; permitirlo dejaría entrar consumo fantasma en la resta.

## Lo que la base NO valida, y por qué

Que `product_id` apunte a un producto `is_sale` y `ingredient_id` a uno
`is_purchase` no se puede expresar en un CHECK — la condición vive en otra
fila. Se valida en la capa de servicio, donde ya se valida el resto del
catálogo (`_validate_products` en `api/delivery_orders.py`).

Tampoco hay `corrects_id`, a diferencia del resto de tablas append-only. Un
ingrediente mal cargado se corrige corrigiendo la línea de pedido completa, que
es la unidad que el operario ve y entiende.

## Decisiones abiertas

**Cómo distingue el sistema un plato fijo de uno armable.** Hoy queda implícito
(tiene filas en `product_recipe` o no tiene), y eso es frágil: un plato fijo sin
receta cargada todavía se ve igual que un armable. Un flag explícito en
`products` es probablemente lo correcto, pero no hace falta para capturar.

**Alias por canal.** Rappi y PedidosYa nombran distinto lo mismo:
"Crispy Salad" / "Bowl crispy", "Filete de Pollo" / "Filete grilled",
"Chucrut clásico púrpura" / "Chucrut col morada topping". Sin una tabla de
alias, un bot que lea el ticket no va a poder matchear contra el catálogo y va a
pedir autorización para crear productos que ya existen.
