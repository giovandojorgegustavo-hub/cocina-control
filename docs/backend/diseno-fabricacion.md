# Diseño — Fabricación de preparados

Estado: **esquema implementado** (migración `0017_fabricacion`, modelos y tests). Falta API y
frontend. Decidido con el dueño el 28 jul 2026.

Revierte la decisión del 13 jul 2026 (*"Sin fabricación"*, `requerimientos.md`).

Este documento se corrigió después de la revisión adversarial de los agentes `qa` y `seguridad`,
que bloquearon la primera versión con 6 críticos y 13 altos. Las secciones de modelo de datos,
integración con stock y visibilidad reflejan lo corregido, no lo propuesto originalmente.

## El problema

La v0.4 resuelve los preparados con una **equivalencia declarada**: el dueño estima que
1 bolsita de quinua cocida ≈ 45,5 g de quinua cruda, y la reconciliación acredita ese
número al contar. Cierra la matemática — pero cierra ciega.

Tres consecuencias, en orden de gravedad:

1. **La merma de fabricación es indistinguible de la fuga.** Si un día el pollo rinde 5
   bolsitas en vez de 6, la equivalencia sigue diciendo 166,7 g por bolsita. El sistema
   reporta 167 g de "fuga de pollo" cuando fue un ave con más hueso. El detector de fugas
   apunta al lugar equivocado.

2. **El factor nunca se aprende.** Es un número estimado a ojo que solo se corrige cuando
   alguien sospecha. Hoy, para las lentejas, es literalmente una corazonada: *"no lo sé,
   pero aprox como quinua porque aumenta"*. Si la lenteja rinde 2,5 y se calcula con 2,2,
   hay 12% de fuga fantasma permanente.

3. **El umbral de tolerancia del 5%** (`requerimientos.md:186`) es un número inventado
   para absorber el error de factores que nadie midió.

Registrar la fabricación convierte el factor en **medido**: `entrada ÷ salida` por batch,
y tras N batches se tiene el rinde real **con su varianza**. El umbral deja de ser una
convención y pasa a ser una propiedad observada de cada producto.

## Principio rector

**Se pesa lo que entra, el sistema dice qué agregar, se cuenta lo que sale.**

```
1. PESÁS lo que entra        →  1,240 kg de filete
2. El sistema MUESTRA           mostaza 124 g · sal 12 g · panko 248 g
   los extras ESCALADOS         harina 99 g · maicena 149 g · huevo 5
3. CONTÁS lo que salió       →  14 milanesas
```

Tres propiedades que sostienen todo el diseño:

**a. El peso disuelve el dato que falta.** La receta del empanizado está expresada "para
1 kg de pollo", pero en la cocina se agarra un puñado de filetes cualquiera. Preguntando
*"¿cuánto pesa un filete?"* nunca se llega — la respuesta de la socia fue *"tipo 12"*, un
número tirado al aire. Pesando, la pregunta deja de existir.

**b. La pantalla le sirve al operario.** No es un trámite para alimentar el tablero del
dueño: le dice cuánto echar. Por eso la va a usar. Una pantalla de fabricación que solo
recolecta datos se abandona en dos semanas.

**c. El único campo obligatorio es la salida.** Y no es trabajo nuevo: el operario ya
cuenta las bolsitas para meterlas a la heladera.

### Por qué la salida NO tiene default aceptable de un click

La tentación es *"quinua → 22 bolsitas por defecto → un click y listo"*. **No.**

Si el operario confirma el default sin contar, la pantalla **fabrica datos falsos**, y eso
es peor que no tener nada. Sin la pantalla, se sabe que el factor es un estimado. Con la
pantalla y el default aceptado a ciegas, el sistema reporta "22 medido", se le cree, y las
fugas fantasma vienen con sello de confirmadas.

**El default va en la ENTRADA** (1 kg de quinua — el operario ya sabe cuánto echó).
**La salida se cuenta.** Es el mismo error que anclar el conteo físico contra el teórico:
medir contra la expectativa destruye la medición.

Si algún batch se confirma sin medir, el registro queda marcado en `measurement` y **no
alimenta la calibración del rinde**. Solo `measured` calibra.

Y el mismo argumento aplica a la **entrada**: pesar tiene más fricción que contar bolsitas, así que
el default de entrada es el más probable de aceptarse a ciegas. Por eso `measurement` distingue qué
lado se midió (`measured` · `default_input` · `default_output` · `both_defaults`) en vez de ser un
booleano atado solo a la salida.

## Las cinco fabricaciones

Un solo formulario. Cero casos especiales.

| Fabricación | Entra (default) | Extras (por receta, escalados) | Sale (se cuenta) |
|---|---|---|---|
| Quinua cocida | 1 kg quinua | — | N bolsitas de 100 g |
| Lentejas cocidas | 1 kg lenteja | — | N bolsitas |
| Pollo deshilachado | 1 kg pollo c/hueso | apio, cebolla roja, sal, ajo, orégano | N bolsitas de 80 g |
| Filete de pollo | 1 kg pollo | — | N filetes |
| Milanesa | 1,2 kg filete | mostaza, sal, huevo, panko, harina, maicena | N milanesas |

Quinua y lentejas tienen el paso 2 vacío. No son un caso aparte: son el caso general con
cero ingredientes extra.

### El pollo fileteado son DOS fabricaciones encadenadas

```
pollo ──[fab 1]──> filete ──[fab 2]──> milanesa
                      │
                      └──> se vende tal cual
```

No es una fabricación con salida múltiple. La evidencia está en cómo lo describe la
socia: *"se agarra un lote grande de filetes"* — los filetes **ya existen** como stock y
se toman después. Filetear y empanizar son hechos separados en el tiempo.

Con un solo registro habría que decidir el destino del lote entero en el momento de
filetear, y no se podrían empanizar mañana los filetes que sobraron. La cocina no
funciona así.

**Precio**: `filete de pollo` pasa a ser producto contable — entra al catálogo y al conteo
físico. No es gratis, pero ya debería estar pasando: hoy hay filetes en la heladera que el
sistema no ve, o peor, que se cuentan como pollo crudo.

### El huevo

Es la única unidad indivisible de las seis. Se redondea a entero **y se guarda el entero**.

Si se guardara `4,96` cuando se pusieron 5 huevos, el teórico quedaría desfasado en cada
batch y los huevos aparecerían con sobrante permanente para siempre. Se guarda lo que
realmente entró.

En pantalla: **"5 huevos"**, editable. Es el único de los seis campos que se toca.

## Modelo de datos

Migración `0017_fabricacion`. **Seis** tablas.

> ⚠️ El número `0017` también está reclamado por `diseno-modificadores-pedido.md`
> (`0017_product_option_groups`), sin implementar. Ésta aterrizó primero; la de modificadores
> pasa a `0018` con `down_revision = "0017_fabricacion"`.

**Éste es un ledger de auditoría.** El operario que registra una fabricación es exactamente la
persona a la que después se le audita el faltante. Cada constraint de abajo existe porque sin ella
hay una forma concreta de inflar el stock teórico y fabricar la coartada del faltante propio. La
base es la última línea de defensa cuando el código de aplicación falla — y la forma de la base es
lo único de esta feature que es difícil de cambiar después.

### Identidad separada de versión

```
manufacturing_recipes            IDENTIDAD — una fila por preparado, para siempre
  id, output_product_id UNIQUE, is_active, created_by, created_at
  UNIQUE (id, output_product_id)          -- target de la FK compuesta

manufacturing_recipe_versions    los parámetros versionados (append-only)
  id, recipe_id FK, input_product_id FK,
  base_input_qty, default_input_qty,
  created_by, created_at, corrects_id, reason
  UNIQUE (id, recipe_id)                  -- target de la FK compuesta

manufacturing_recipe_items       los extras — cuelgan de la IDENTIDAD
  id, recipe_id FK, product_id FK, qty_per_base,
  rounding ('exact'|'integer'), position,
  created_by, created_at, corrects_id, reason
```

**Por qué los items cuelgan de la identidad y no de la versión.** Si colgaran de la versión, crear
una v2 para cambiar `default_input_qty` la dejaría sin items — y mostaza, sal, huevo, panko, harina
y maicena dejarían de descontarse **en silencio**. Seis productos con sobrante teórico creciente y
permanente, que es la forma exacta que tiene una fuga real de quedar enmascarada. Nadie mira el
panko. Los items se versionan individualmente por su propio `corrects_id`.

**Por qué `output_product_id` vive en la identidad y es UNIQUE.** Cuando vivía en la fila
versionada, una cadena de `corrects_id` podía secuestrar la receta hacia otro producto y dejar dos
recetas vigentes para el mismo preparado. "La receta de la milanesa" tenía dos respuestas.

### El hecho: la fabricación

```
manufacturing_batches            el hecho ocurrido — INMUTABLE
  id, recipe_id, recipe_version_id, output_product_id,
  output_qty,                              -- LO CONTADO
  measurement ('measured'|'default_input'|'default_output'|'both_defaults'),
  validated_at, validated_by, created_by, created_at
  FK (recipe_id, output_product_id) -> manufacturing_recipes
  FK (recipe_version_id, recipe_id) -> manufacturing_recipe_versions

manufacturing_batch_inputs       snapshot de lo consumido (append-only)
  id, batch_id FK, product_id FK, qty, is_primary,
  created_by, created_at, corrects_id, reason

manufacturing_batch_events       anulación (append-only, owner/admin)
  id, batch_id FK, event_type ('annulled'), reason NOT NULL,
  created_by, created_at
```

**`manufacturing_batches` NO guarda `input_qty`.** El peso que entró es **un** hecho y vive en **un**
lugar: el insumo primario. Cuando estaba duplicado se podía reportar un rinde impecable
(`input_qty = 1` → 22/1) mientras el inventario descontaba otra cosa (`qty = 6`). Ésa era la
coartada: el número que el dueño mira para detectar anomalías y el número que mueve el inventario
eran variables independientes.

**Las dos FK compuestas** hacen imposible —no improbable, imposible— que un batch acredite
producción a un producto distinto del de su receta, o que use la versión de otra receta.

**`manufacturing_batch_inputs` es un snapshot**, no un puntero a la receta: guarda cantidades, igual
que `delivery_items`. Si la receta cambia mañana, los batches viejos no se mueven.

### Reglas que no se pueden expresar como CHECK

Viven en triggers de la migración. Están documentadas en cada modelo para que no se pierdan al leer
solo el esquema.

| Regla | Por qué | Cómo |
|---|---|---|
| Exactamente **un** insumo primario vigente por batch | Sin esto, un batch sin inputs crea stock de la nada; y corrigiendo un extra con `is_primary=true` quedan dos y el peso de referencia deja de ser único | constraint trigger `DEFERRABLE INITIALLY DEFERRED` |
| El primario tiene que ser el `input_product_id` de la versión usada | Si no, se descuenta el producto caro y se reporta el rinde del barato | mismo trigger |
| `created_by = validated_by`, `validated_at` en las últimas 24 h y no futuro | La bandeja muestra "fabricó X": esa firma no puede ser un campo libre. Un batch retroactivo cambia el teórico de un período ya conciliado | trigger `BEFORE INSERT` |
| Recetas, versiones, items y anulaciones: solo owner/admin | Los batches deliberadamente **no** llevan guard: fabricar es del cocinero, que es el punto de toda la feature | `cocina_require_admin_or_owner_creator()` de `0013` |
| UPDATE y DELETE prohibidos en las seis tablas | El repo llamaba "append-only" a tablas que a nivel base aceptaban UPDATE y DELETE físico. Acá la inmutabilidad se declara como propiedad del diseño, así que se enforcea: un UPDATE reescribía la receta **y su autoría** | `cocina_forbid_update_delete()` |

### `measurement`: el anti-anclaje aplica a los dos lados

El argumento contra el default en la salida vale igual para la entrada — y **pesar tiene más
fricción que contar bolsitas**, así que el default de entrada es el más probable de aceptarse a
ciegas. Si el cocinero echa 1,15 kg y el campo dice 1,000, los **dos** números que alimentan al
detector quedan mal a la vez: el descuento de stock y el rinde.

Solo `measurement = 'measured'` calibra el rinde.

### Anulación: un error congelado no es trazabilidad

Un batch es inmutable, pero un batch cargado por error tiene que poder anularse. Sin eso, un
"220 bolsitas" tipeado con un cero de más infla el stock **y corre el umbral de detección del
producto para siempre**, porque el umbral sale de la varianza del rinde.

Espeja `purchase_order_status_events`: evento inmutable, motivo obligatorio no vacío, guard de rol.
El cocinero registra; anular es del dueño.

### La flag en `products`

`ck_products_purchase_or_sale` pasa a `is_purchase OR is_sale OR is_manufactured`.

| Producto | purchase | sale | manufactured |
|---|:---:|:---:|:---:|
| Quinua cruda | ✅ | ❌ | ❌ |
| Quinua cocida (bolsita) | ❌ | ❌ | ✅ |
| Filete de pollo | ❌ | ✅ | ✅ |
| Milanesa | ❌ | ✅ | ✅ |

`ProductCreate`, `ProductUpdate` y las respuestas exponen la flag: sin eso, **la quinua cocida es
increable por el único camino que existe** y la feature no arranca.

El `downgrade()` chequea si hay preparados puros antes de recrear el CHECK viejo, y falla con un
mensaje que dice qué resolver — en vez del `CheckViolation` crudo de Postgres.

## Integración con el cálculo de stock

**Éste es el punto donde la feature se rompe si se ignora.**

No hay tabla de stock: `services/dashboard.py:_compute_stock_now` (l.291-348) lo calcula on-demand.
La fórmula pasa a:

```
stock = último conteo confirmado
      + entradas   (leaf delivery_items,        > last_count_at)
      − salidas    (leaf delivery_order_items,  > last_count_at)
      + Σ batches.output_qty                    (> last_count_at, no anulados)
      − Σ batch_inputs.qty  [HOJAS]             (> last_count_at, no anulados)
```

Tres filtros que **no** son opcionales y que la primera versión de este documento omitía:

1. **Ancla temporal.** `_entries_qty_since` / `_orders_qty_since` filtran `> last_count_at`. Sin ese
   filtro, todo batch anterior al último conteo se suma **dos veces**: una dentro del conteo físico
   y otra por la fórmula.
2. **Filtro leaf.** `manufacturing_batch_inputs` tiene `corrects_id`. Sumar `qty` sin resolver la
   cadena **descuenta doble cada input corregido**. Usar `_leaf_ids_for_items`, que existe
   precisamente para esto.
3. **Excluir anulados.** Un batch con evento `annulled` no mueve stock ni calibra rinde.

Con eso la fabricación es contablemente **neutra**: el insumo se va del estante y vuelve como
preparado. La diferencia con la equivalencia declarada es que ahora el factor es un hecho
registrado.

### La equivalencia deja de declararse

```
rinde = media de (output_qty / qty del insumo primario hoja)
        agrupado por (recipe_id, input_product_id)
        donde measurement = 'measured' y el batch no está anulado
```

**Por `(recipe_id, input_product_id)`, no por producto de salida.** Una versión puede cambiar el
insumo (pollo entero → pechuga) y promediar kg con unidades da un número sin significado.

Su desviación estándar alimenta el umbral de tolerancia por producto, que hoy es un 5% global
inventado. Las lentejas dejan de ser una corazonada al primer batch registrado.

## Roles y visibilidad

| Acción | Dueño | Admin | Cocinero |
|---|:---:|:---:|:---:|
| Definir/editar recetas y versiones | ✅ | ✅ | ❌ |
| Registrar una fabricación | ✅ | ✅ | ✅ |
| Anular un batch | ✅ | ✅ | ❌ |
| Ver la bandeja de fabricados | ✅ | ✅ | ✅ |
| **Ver rinde acumulado y varianza** | ✅ | ❌ | ❌ |

Esta matriz tiene que reflejarse en la tabla canónica de `requerimientos.md`, no vivir solo acá.

### El principio del operario, corregido — y el carve-out que se fue de más

`requerimientos.md` decía: *"El operario no ve recetas, factores, equivalencias, teóricos ni
discrepancias en ninguna ruta ni pantalla"*. El dueño lo declaró sobre-amplio (28 jul 2026), con
razón: esconderle la receta a quien la cocina no protege nada.

Pero la primera reescritura de este documento se llevó de más **dos** cosas, y hay que decirlo
porque es el error más instructivo de todo el diseño:

| | Regla vigente |
|---|---|
| Recetas de producción | ✅ Las ve. Es instrucción de trabajo |
| Costos y plata | ❌ Ocultos siempre |
| Teórico y discrepancia | ❌ **Ninguna pantalla de captura los muestra, para ningún rol** |
| **Rinde acumulado y su σ** | ❌ **Solo el dueño** |

**Lo que se cayó y por qué importa:**

1. **El rinde quedó sin cobertura.** Y el rinde con su desviación estándar **es el umbral de
   detección**. Quien lo ve sabe exactamente cuánto puede sacar por batch sin disparar la alerta.
   Eso es anti-fraude puro; el razonamiento anti-anclaje no lo cubría.
2. **Se concedió la discrepancia "después de confirmar el conteo".** El fundamento anti-anclaje
   justifica una restricción de **orden**, no una concesión de **acceso**. Mostrarle al cocinero la
   discrepancia del ciclo N le da el mapa de residuales para el ciclo N+1 — *"la palta siempre sale
   +200 g, ahí hay margen"*. Y `api/dashboard.py` ya lo tiene cerrado con `require_role("owner")`:
   el criterio nuevo **abría** una puerta que el código tenía cerrada.

La lección, que vale más que el caso: **un principio se escribe con su fundamento al lado.** Cuando
un enunciado agrupa tres reglas con fundamentos distintos, la más débil arrastra a las otras al
revisarlo. Con el fundamento explícito, el carve-out es obvio y no se lleva puesto lo que cubría
otra amenaza.

**REGLA DE ORO**: los schemas de fabricación no tienen campos monetarios. Test obligatorio iterando
claves prohibidas — y la lista se amplía más allá de lo monetario: `expected_qty`, `theoretical`,
`discrepancy`, `rinde`, `yield_factor`, `variance`, `stddev`.

## API

Router `manufacturing.py`, prefijo `/api/v1/manufacturing`. Rutas literales antes de las
paramétricas.

| Ruta | Rol | Qué hace |
|---|---|---|
| `GET /manufacturing/recipes` | cualquiera | preparados fabricables, con su default de entrada |
| `GET /manufacturing/draft?recipe_id=&input_qty=` | cocinero/admin | **escala los extras**; no crea nada en DB |
| `POST /manufacturing/batches` | cocinero/admin | registra el batch + sus inputs, en un solo POST |
| `GET /manufacturing/batches` | cualquiera | la bandeja de fabricados, `validated_at DESC` |
| `POST /manufacturing/recipes` | owner/admin | crea/versiona receta |

`GET /draft` es el corazón de la pantalla: recibe el peso, devuelve los extras escalados y
redondeados. Espeja `GET /purchase-orders/{id}/partida-draft` — pre-poblar sin persistir.

`POST /batches` sigue el patrón de `POST /purchase-orders/{id}/partidas`: nace `validada`,
con `validated_at`/`validated_by`, sin máquina de estados intermedia. Se registra un hecho
consumado, no se abre un flujo.

## Frontend

- Botón **FABRICAR** en `pages/Home.tsx` (l.83-90), junto a ENTRADA / INVENTARIO / PEDIDO.
- `pages/BandejaFabricacion.tsx` — espeja `BandejaPartidas.tsx`: lista de preparados
  fabricables arriba, registro de fabricados abajo con `formatRelativeDate` y
  `· fabricó {validated_by_name}`.
- `pages/RegistroFabricacion.tsx` — espeja `VerificacionPartida.tsx`: `useReducer`, teclado
  numérico, filas de `min-h-[48px]`, POST único al final.
- Hooks en `lib/manufacturing.ts`, tipos en `lib/types.ts`, `staleTime: 0`,
  `networkMode: 'offlineFirst'`, `userId` en el `queryKey`.

## Qué queda afuera

- **Trazabilidad de lotes** (vencimientos, qué batch salió en qué pedido). Sigue fuera de
  alcance, como en `requerimientos.md:256`.
- **Multi-tenant / benchmark de rinde entre cocinas.** Es el destino declarado del dueño,
  pero no condiciona nada de este diseño.
- **Fabricación planificada** ("hay que hacer 3 batches de quinua"). Se registra lo que
  pasó, no lo que debería pasar.
- **Corrección de un batch ya registrado.** Se ancla al patrón de ventana temporal de
  `deliveries`/`inventory`, pero se especifica en un segundo paso.

## Cambios en documentos existentes

- `requerimientos.md:26` — el punto 2 "Sin fabricación" se revierte.
- `requerimientos.md:256` — sale de la lista de no-alcance.
- `requerimientos.md:154` (sección E) — la equivalencia pasa de declarada a derivada.
- `requerimientos.md:310` — el principio del operario, corregido según la tabla de arriba.
- `requerimientos.md:186` — el umbral por producto se alimenta de la varianza medida.
