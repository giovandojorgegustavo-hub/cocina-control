# Decisiones de backend — Catálogo de venta de Bonabowl

Decisiones tomadas al cargar por primera vez el catálogo de productos de venta
(`src/cocina_control/scripts/seed_sale_products.py`, PR #156). Se documentan acá
porque tienen consecuencias directas sobre el cálculo de consumo teórico, y un
comentario en el código se pierde en el próximo refactor.

Fuente del catálogo: menú publicado de **Bonabowl - Orbea** en Rappi
(`rappi.com.pe/restaurantes/86834-bonabowl`), consultado el **28 jul 2026**.
Secciones tomadas: *Personaliza Tu Plato*, *Bowl*, *Wraps*, *Bebidas*, más las
salsas del paso *Elige la salsa de tu bowl*.

---

## D1 — Los combos NO son productos

> ¿"Combo office" (1 bowl + 1 bebida + 1 salsa) entra al catálogo?

**No.** Un combo es una **combinación** de productos que ya están en el
catálogo. Registrarlo como producto propio haría que el mismo bowl se cuente dos
veces cuando se calcule el consumo teórico: una por el combo y otra por el bowl.

El detector de fugas mide exactamente esa diferencia entre teórico y real
(`docs/requerimientos.md` §Alcance v0.4). Duplicar el teórico arruina el único
número que el sistema existe para producir.

**Cómo se hace cumplir:** `test_catalogue_has_no_combos` falla si alguien mete un
nombre con "COMBO" en `SALE_CATALOGUE`.

**Consecuencia operativa:** cuando salga un combo, el operario registra los
productos que lo componen, no el combo. Si eso resulta molesto en la práctica, la
solución es una pantalla que expanda el combo en sus componentes — nunca un
producto "combo" en la tabla.

---

## D2 — El script nunca muta un producto existente

> Si un nombre del catálogo ya existe en la base, ¿el script lo corrige?

**No. Lo reporta y sale con código 2.** El script solo inserta lo que falta.

Motivo: `products` no tiene tabla de historial. El modelo lleva un único par
`updated_by` / `updated_at` que se pisa en cada mutación, así que un cambio en
lote no deja rastro de qué había antes. Para un sistema donde el que registra es
también el que después se audita, una mutación masiva sin historial es
inaceptable (`.claude/contexto-producto.md`, restricción #2: nada se edita sin
rastro).

La ruta con auditoría para resolver un conflicto es `PATCH /products/{id}`:
owner solamente, de a una fila, con un humano en el loop.

Los dos conflictos que el script reporta:

| Caso | Qué significa |
|---|---|
| `existe pero NO está marcado como venta` | Hay una fila con ese nombre cargada como insumo de compra. Promoverla a venta es decisión del dueño. |
| `ya existe con otra grafía` | Colisión semántica (acentos o mayúsculas). Crear la fila igual dejaría dos productos gemelos en la grilla del pedido. |

---

## D3 — `is_purchase AND is_sale` NO significa "mal marcado"

> ¿Se puede limpiar automáticamente el `is_sale` de los insumos crudos?

**No, y este es el punto más importante del documento.**

La primera versión del script traía un flag `--fix-mismarked` que desmarcaba
`is_sale` en todo producto que fuera `is_purchase AND is_sale AND` no estuviera
en el menú. La heurística era: "si se compra y se vende, y no está en la carta,
es un insumo mal flageado".

**Es falsa.** La migración `0015_product_purchase_sale_flags` documenta el caso
legítimo de forma explícita:

> "Un producto puede ser ambos (ej. gaseosa que se compra y se vende tal cual)."

Toda reventa — gaseosa, agua, snack, postre comprado hecho — cumple las tres
condiciones. El flag se las llevaba puestas. Y un producto que sale de la grilla
de venta pasa a figurar como stock que entró y nunca salió: **una fuga fantasma**.

**Decisión: no hay señal en los datos que distinga una reventa de un insumo mal
marcado.** Mientras no exista esa señal, adivinar por heurística está prohibido.
El script se limita a **listar** los productos marcados como venta que no están
en el menú, para que el dueño los revise de a uno.

**Deuda abierta:** si la limpieza a mano se vuelve pesada, la solución es agregar
la señal que falta (una columna de procedencia, o una lista explícita de
reventa), no afinar la heurística.

---

## D4 — Comparación de nombres insensible a acentos y mayúsculas

> ¿`MARACUYÁ` y `MARACUYA` son el mismo producto?

**Para comparar, sí. Para guardar, se respeta el acento.**

La API normaliza los nombres con `strip + collapse + upper` (`schemas/product.py`)
pero **no toca los acentos**, y el índice único parcial
`ix_products_name_active_unique` es sobre el texto plano. O sea: para Postgres
son dos filas distintas, y para el operario apurado son el mismo producto en la
grilla.

Un duplicado semántico es peor que un producto faltante: el faltante se nota, el
duplicado no — y parte las ventas del mismo ítem en dos series, ensuciando la
fuga calculada en ambas direcciones.

`_normalise_key()` (NFKD + descarte de combinantes + upper) es la clave de
comparación. El nombre que se guarda conserva su acento correcto.

**Deuda abierta:** la API no aplica esta normalización. Un producto creado desde
el alta inline de `CompletarPedido.tsx` todavía puede generar el gemelo.
