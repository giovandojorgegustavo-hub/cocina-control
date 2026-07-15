# Requerimientos v0.4 — Cocina Control

Sistema para que el dueño de una dark kitchen detecte fugas de inventario sin cambiarle la vida al operario. En v0.2 capturamos hechos crudos (qué llegó verificado, qué se empacó con foto, qué queda) y mostramos consumo por diferencia en cantidades. En v0.3 sumamos dos capacidades para que el dueño pueda tomar decisiones con datos completos: **saber cuánto le cuesta el inventario y el consumo**, y **registrar entregas que llegan en varias tandas**. En v0.4 llega el corazón del sistema: **la caza de fugas** — catálogo con unidades naturales y conversión, recetas estimadas por plato y reconciliación teórico vs. real. Con una decisión de diseño deliberada: **cero registros nuevos para la operación diaria** — una entrada (compras), una salida (pedidos), y el conteo periódico que ya existe.

## Contexto

- **Negocio:** dark kitchen con 4 operarios part-time en Lima. Un operario por turno, cada uno trabaja 3 o 4 días por semana.
- **Problema:** el dueño sospecha fugas de inventario. El control es manual: llega una hoja con las compras, se confía que vino completo, cada tanto se cuenta lo que queda, y el dueño calcula consumos a mano restando inventarios.
- **Objetivo v0.3:** consolidar v0.2 con **plata** (costos por lado del dueño) y **partidas** (una orden puede recibirse en varias tandas). Ambos requerimientos vienen de la operación real de las últimas semanas: proveedores que entregan fraccionado y decisiones de compra que hoy se toman sin ver el costo de lo que se está consumiendo.
- **Objetivo v0.4:** cerrar el círculo del detector de fugas. El dueño define recetas estimadas por plato; el sistema calcula el consumo teórico de cada insumo crudo a partir de lo vendido; cada conteo de inventario se compara contra ese teórico. **La diferencia sin explicar es la fuga.**

### Cambios respecto de v0.2

v0.2 asumía dos cosas que la operación real desmintió:

1. **Una entrega = una llegada.** Los proveedores entregan **fraccionado**: la orden de 100kg de pollo llega como 30 el lunes, 40 el martes, 30 el jueves. Hoy el operario tiene que decidir si valida "lo que llegó hasta ahora" o esperar a que se complete — cualquiera de las dos rompe la trazabilidad. v0.3 acepta explícitamente **recepciones por partidas**: cada tanda se pesa y registra por separado, sumando hasta cerrar la orden.
2. **El sistema no habla de plata.** El dueño mide cantidades y calcula "cuánto me costó" a mano, en Excel. Los pedidos grandes se deciden sin ver el costo de lo que ya está en stock ni el costo del consumo del período. v0.3 agrega **costos del lado del dueño** (el operario nunca ve plata, ni siquiera de reojo). Habilita costo de inventario y costo de consumo — cálculos posteriores, no en el momento de captura.

### Cambios respecto de v0.3

Las 8 decisiones abiertas de v0.3 fueron respondidas por el dueño en el PR #95: costo al comprar, cierre automático reabrible, el operario registra la partida, costo por unidad, valuación del consumo (revisada después a **FIFO por partidas** — ver decisión abajo), exceso permitido y registrado como discrepancia, anular conserva las partidas recibidas, 2 decimales. v0.4 asume esas respuestas — en particular el FIFO por partidas, que es la base para valuar las fugas en plata y habilita los **ajustes de entrada/salida** del conteo.

v0.4 rompe una asunción de v0.3 y toma dos decisiones de diseño nuevas:

1. **Los productos dejan de ser islas — llegan las recetas.** El principio #4 ("productos como items independientes") se rompe deliberadamente, pero **solo del lado del análisis**: cada plato vendido tiene una receta estimada que se traduce en consumo teórico de insumos crudos. La captura no cambia: el operario sigue registrando compras, pedidos y conteos exactamente igual.
2. **Sin fabricación.** La primera versión de este alcance incluía registrar la producción de intermedios (maracuyá procesado, salsas). El dueño la descartó (13 jul 2026): las recetas se **aplanan hasta el insumo crudo** — el bowl consume palta y yogurt, no "guacamole" — y los preparados que aparezcan en el conteo se resuelven con una **equivalencia** (ver sección E). Resultado: una sola entrada (compras), una sola salida (pedidos), cero pantallas nuevas para el operario.
3. **Las cantidades ahora tienen unidad declarada.** La planilla real mezcla unidades por producto (paltas por unidad, espinaca en gramos, piña en latas, grapas en cajas de 10). El catálogo normaliza esto: cada producto declara su unidad natural y, si participa en recetas por peso, su factor de conversión a gramos.

## Alcance v0.3

Los tres registros de eventos de v0.2 se mantienen; se agregan dos nuevos y un tablero enriquecido.

| Registro | Cuándo se usa | Qué se anota | Cambia en v0.3 |
|---|---|---|---|
| **Entrada** | Llegó una tanda de una orden anunciada | Verificación de la lista pre-cargada: qué llegó y cuánto | Sí — puede haber varias por orden |
| **Pedido** | Se empaca un pedido para despachar | Foto del paquete al momento; productos incluidos, después | No |
| **Inventario** | Periódico o a pedido del dueño | Cuánto queda de cada producto | No |
| **Orden de compra** *(nuevo)* | El dueño planea/pide una compra al proveedor | Proveedor, productos, cantidades esperadas, **costo** | Nuevo en v0.3 |
| **Costo de partida** *(nuevo)* | Se registra cuánto costó lo que efectivamente llegó | Costo por ítem de la tanda recibida | Nuevo en v0.3 |

**Tablero del dueño** (sólo lectura, sólo dueño):

- Consumo por diferencia (en cantidades) — v0.2, sin cambios.
- Stock actual por producto (en cantidades) — v0.2.
- Productos por acabarse — v0.2.
- **Costo de inventario** (nuevo): cuánta plata hay parada en depósito.
- **Costo de consumo del período** (nuevo): cuánta plata se consumió, calculada del lado del dueño con los costos que él registró.
- **Órdenes de compra abiertas** (nuevo): cuántas órdenes están recibidas parcialmente y cuánto falta.

Los productos siguen siendo items independientes en v0.3. (Cambia en v0.4 — ver **Alcance v0.4**: recetas del lado del análisis, captura intacta.)

### A. Costos — plata del lado del dueño

El dueño registra el costo de lo que compra. El **operario nunca ve plata** — sigue verificando cantidades a ciegas, exactamente como en v0.2. El sistema respeta el principio no negociable #1 ampliado: *el operario no ve análisis ni plata*.

**Cómo el costo entra al sistema:**

- Cuando el dueño pre-carga una orden de compra, escribe también el costo esperado por ítem.
- El costo del inventario y del consumo se calculan post-facto sobre los costos registrados por el dueño.
- El operario ni ve el precio, ni lo tipea, ni lo escucha. No aparece en su tablet ni en ninguna pantalla que él pueda abrir.

> **DECISIÓN RESUELTA (PR #95) — momento del cargo del costo: al comprar.**
> El dueño carga el costo junto con la orden, factura en mano; el operario nunca toca plata. Si el precio final difiere, la corrección es un registro nuevo sobre la orden (append-only), no una reapertura destructiva.

> **DECISIÓN RESUELTA (PR #95) — granularidad del costo: por unidad.**
> El dato base es el costo unitario; el sistema calcula y muestra el total (unidad × cantidad). Con partidas, cada tanda cuesta `cantidad × precio unitario` sin cuentas manuales, y los precios variables entre compras (pollo a 7, a 6, a 8) se registran sin fricción.

> **DECISIÓN RESUELTA (revisada 13 jul 2026) — método de valuación del consumo: FIFO por partidas.**
> Decisión original (PR #95): promedio ponderado. **Revisada por el dueño**: FIFO como convención contable — el consumo agota partidas en papel, la más vieja primero, sin pretender saber qué kilo físico salió de qué tanda. Razones: (1) es el modelo mental con el que el dueño ya opera, (2) es el diseño probado de NuevosistemaOFICIAL (`aplicar_salida_partidas` FIFO por fecha, `partida_afectada` para trazabilidad), (3) deja ver el remanente por partida ("quedan 2 kg de la tanda del martes") y valúa el inventario a precios recientes.
>
> Reglas de borde:
> - **Consumo** agota partidas de la más vieja a la más nueva. El costo del consumo es la suma de lo agotado de cada partida.
> - **Conteo con sobrante** → **ajuste de entrada**: el excedente entra como partida de ajuste valuada al costo de la última partida del producto.
> - **Conteo con faltante** → **ajuste de salida**: el faltante consume partidas igual que un consumo (más vieja primero).
> - Los ajustes son eventos append-only con quién/cuándo/motivo, como todo.
> - La valuación es **minería posterior**: partidas remanentes y agotamientos se derivan de los eventos y son recomputables desde cero — ninguna pantalla de captura depende de este cálculo.
> - **Corrección de costo → recalcula (decisión del dueño, 15 jul 2026).** Corregir el costo de una compra arregla un ERROR sobre un hecho pasado (la factura siempre dijo el valor correcto); las valuaciones derivadas (costo de consumo, ajustes valuados, tablero) se recomputan con el costo corregido, también hacia atrás. El "rige hacia adelante" queda reservado para cambios de CRITERIO: recetas y factores de conversión (v0.4). Los eventos crudos jamás se recalculan — solo los números derivados.

### B. Recepción por partidas

Una **orden de compra** al proveedor puede recibirse en varias **partidas** (tandas). Cada partida se registra por separado en el mismo flujo de "entrada" que ya conoce el operario. La orden se cierra cuando la suma de las partidas cubre lo pedido — o cuando el dueño decide cerrarla aunque falte.

**Cómo funciona en la operación:**

- El dueño pre-carga una **orden de compra** con proveedor, productos, cantidades esperadas y costo (ver sección A). La orden arranca en estado **abierta**.
- El proveedor entrega una tanda. El operario abre la orden abierta en su bandeja y registra una **partida**: producto por producto, pesa y anota la cantidad recibida en esa tanda. Igual que la verificación de v0.2, con el flujo optimista de "OK — llegó así" en los ítems que llegaron completos.
- Al validar la partida, **el stock se actualiza inmediatamente con lo que llegó en esa partida**. No espera a que la orden se cierre.
- La orden queda en estado **recibida parcialmente**. En la bandeja del operario sigue apareciendo, ahora con un resumen de "faltan 40kg de pollo" (o similar) para el próximo turno.
- Cuando llega la siguiente tanda, mismo flujo. El operario ve el resto pendiente y registra una partida nueva.
- La orden pasa a estado **cerrada** cuando se cumple la condición de cierre (ver decisión abajo).

**Lo que no cambia**: la validación de cada partida sigue siendo del operario, sigue siendo <5s por ítem, sigue siendo append-only (cada partida es un registro nuevo).

> **DECISIÓN RESUELTA (PR #95) — cierre de orden: automático al completarse, reabrible.**
> La orden se cierra sola cuando el saldo por producto llega a 0. El dueño puede reabrirla si el proveedor manda algo más o si hubo un error. Cerrar y reabrir son eventos append-only.

> **DECISIÓN RESUELTA (PR #95) — quién registra la partida: el operario.**
> Es quien está en la cocina pesando lo que llega — mismo flujo que la verificación de v0.2, sin esperar al dueño. Un doble-check agregaría fricción contra la regla de los 5 segundos.

> **DECISIÓN RESUELTA (PR #95) — exceso de partida: se acepta y se registra como discrepancia.**
> La partida completa entra al stock (lo que llegó es real); el excedente sobre la orden queda marcado como discrepancia visible para el dueño en su tablero. No se bloquea la realidad — se la muestra.

> **DECISIÓN RESUELTA (PR #95) — cancelación con partidas recibidas: anular es una corrección.**
> Las partidas ya recibidas quedan como registros (impactaron stock real); la orden pasa a estado **anulada** con motivo. El stock no se revierte. Respeta append-only y auditoría.

## Alcance v0.4 — el detector de fugas

Ningún registro nuevo para el operario. Todo v0.4 vive en dos lugares: el **catálogo** (lado dueño) y la **minería posterior** (tablero). La operación diaria sigue siendo: verificar partidas, foto + completar pedidos, contar cuando toca.

### El inventario real (referencia de diseño)

La planilla semanal del negocio (CW Kitchen Group SAC, "Inventario Semanal") cuenta ~60 productos en 5 categorías. Esta planilla es el contrato de realidad del catálogo:

| Categoría | Ejemplos | Unidades reales de conteo |
|---|---|---|
| Productos frescos | palta, lechuga, tomate, espinaca, huevo, queso fresco, maracuyá | unidad, gramos, fracción de atado (¼ de apio) |
| Salsas | salsa BBQ (preparada en cocina), mayonesa | gramos |
| Congelados | pollo deshilachado, milanesa, filete de pollo, hamburguesa, tocino | unidad |
| Condimentos | sal, ajinomoto, ají panka, quinua, frejol, mostaza, piña, pan molde | gramos, lata, unidad |
| Packing y limpieza | bolsa, bowl 1300 ml, tapa, ajicero, tenedor, cuchillo, papel toalla, detergente, grapas | unidad, caja (de 10) |

Tres hechos de la planilla mandan sobre el diseño:

1. **Unidades heterogéneas y mal normalizadas**: la misma hoja escribe "Und/Und./Unnd" y "Gr./Gram/Gramos". El sistema define un catálogo de unidades cerrado; cada producto usa exactamente una.
2. **Hay preparados en el conteo**: maracuyá procesado (1500 g) y salsa BBQ (420 g) se cuentan aunque se preparen en cocina — ver sección E.
3. **Hay productos sin receta de comida**: detergente y papel toalla se cuentan pero no participan del teórico por platos. El packing (bowl, tapa, cubiertos, bolsa) sí se consume por pedido.

### C. Catálogo: unidad natural + conversión

Cada producto se registra y se cuenta SIEMPRE en su **unidad natural** — la misma con la que el negocio ya piensa: paltas por unidad, espinaca en gramos, piña en latas. Nadie convierte nada en el momento de captura.

- El catálogo de unidades es cerrado y normalizado (unidad, gramo, lata, caja…). Se acabó el "Und/Unnd/Gram".
- Los productos que participan en recetas por peso declaran un **factor de conversión a gramos** (1 lechuga ≈ X g). Lo define el dueño, es editable, y cada cambio es un registro nuevo que rige **hacia adelante** — los teóricos ya calculados no cambian retroactivamente.
- Los **5 platos del negocio** (Bacon Fit, BBQ, bonabowl, andes, influencer) son productos del catálogo, tipo "plato". El operario ya los usa al completar pedidos desde v0.2 — su flujo no cambia en nada.

> **DECISIÓN RESUELTA (PR #96) — calibración de factores de conversión: estimado ajustable.**
> Se arranca ya, con números gruesos del dueño. Consecuencia asumida: las primeras reconciliaciones mostrarán discrepancias que son error de factor, no fuga — el tablero y el onboarding deben comunicarlo (si un producto "fuga" siempre el mismo %, el factor está mal calibrado; se ajusta y recién después el rojo significa fuga).

### D. Recetas estimadas por plato

La receta es la traducción de un plato vendido a insumos crudos consumidos. Es un **estimado del dueño**, no una fórmula de cocina: existe para calcular consumo teórico, no para decirle al operario cómo cocinar.

- Cada plato tiene una lista de insumos crudos con cantidad estimada (en gramos o en unidad natural, según el producto).
- **Aplanada hasta el crudo**: si el bowl lleva guacamole, la receta dice palta y yogurt — el intermedio no existe como paso.
- Las define y edita **solo el dueño**. Cada cambio es una versión nueva append-only que rige hacia adelante: el teórico de períodos pasados se calculó con la receta vigente entonces y no se recalcula.
- **El operario jamás ve una receta.** Ni al completar pedidos, ni en ninguna pantalla de su rol.

> **DECISIÓN RESUELTA (PR #96) — packing dentro de la receta: sí.**
> La receta del plato incluye el packing (1 bowl 1300 ml, 1 tapa, 1 tenedor, 1 cuchillo, 1 bolsa, ajiceros según plato). El teórico cubre también los descartables — ahí también hay fuga.

> **DECISIÓN RESUELTA (PR #96) — merma esperada: adentro del estimado de la receta.**
> Un solo número por ingrediente: la receta dice "120 g de palta" ya contando cáscara y pepa. La receta estima consumo de compra, no de plato servido.

### E. Preparados: equivalencia, no fabricación

Los preparados (maracuyá procesado, salsa BBQ) **no se registran cuando se hacen** — decisión deliberada del dueño. Pero aparecen en el conteo físico, y si el sistema los ignorara, cada batch a medio usar se leería como fuga falsa: las paltas "desaparecieron" pero el guacamole está en la heladera.

La solución es una **equivalencia en el catálogo**, no un registro:

- El preparado existe como producto contable con su **receta de equivalencia**: "1000 g de salsa BBQ ≈ X g de tomate + Y g de azúcar + …". La define el dueño, versionada igual que las recetas.
- El operario lo cuenta en el inventario como cualquier producto — a ciegas, como siempre.
- La minería posterior convierte lo contado a crudos equivalentes y **acredita** esos crudos en la reconciliación. El medio batch de maracuyá deja de ser fuga fantasma.
- Cero pantallas nuevas, cero pasos nuevos: es un producto más en el conteo + un cálculo del lado del análisis.

Ejemplo con números de la planilla: el conteo encuentra 1500 g de maracuyá procesado. Su equivalencia dice que 1000 g de pulpa ≈ 1450 g de fruta. La reconciliación acredita ~2175 g de maracuyá fruta al "real disponible" antes de comparar contra el teórico.

### F. Reconciliación teórico vs. real

El detector de fugas. Corre en la minería posterior, entre dos conteos de inventario:

```
stock teórico  =  conteo anterior confirmado
               +  entradas del período (partidas validadas)
               −  consumo teórico (platos vendidos × receta vigente)

discrepancia   =  stock teórico − conteo actual
                  (con preparados convertidos por equivalencia)
```

- La discrepancia se reporta **por producto**, en unidad natural y en plata (valuada por FIFO por partidas, la decisión revisada de v0.3: el faltante se valúa como ajuste de salida — partidas más viejas primero; el sobrante como ajuste de entrada al costo de la última partida).
- El tablero del dueño muestra: discrepancia por producto del período, ranking de productos con mayor fuga en soles, y evolución entre conteos.
- **El operario no ve nada de esto.** Sigue contando a ciegas — el principio #1 es exactamente lo que hace confiable al conteo que alimenta este cálculo.
- Toda discrepancia es reconstruible: el dueño puede abrir un producto y ver los eventos que componen el teórico (conteo anterior, cada partida, cada pedido cuya receta usa ese insumo).

> **DECISIÓN RESUELTA (PR #96) — umbral de tolerancia: 5% de default global, ajustable por producto.**
> Ninguna cocina cuadra a cero: el umbral separa ruido normal (balanza, factores estimados) de "acá hay algo". El dueño puede ajustar el % por producto — el culantro merma distinto que los tenedores.

## Roles y permisos (revisión del dueño, 13 jul 2026)

El modelo binario dueño/operario se amplía a **tres roles**. Decisión del dueño: el operario-admin **ve y carga costos** igual que el dueño (opción B).

| Rol | Crear órdenes (con costos) | Recibir partidas | Contar inventario | Empacar pedidos | Tablero |
|---|---|---|---|---|---|
| **Dueño** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Admin** | ✅ | ✅ | ✅ | ✅ | ❌ |
| **Cocinero** | ❌ | ✅ | ✅ | ✅ | ❌ |

La regla que NO cambia — y que reformula el principio #1: **la plata vive en las pantallas administrativas, no en las de captura**.

- Crear/editar orden de compra, historial de costos, tablero → muestran plata; accesibles según la tabla.
- Verificar partida, contar inventario, empacar pedido → **no muestran plata para NINGÚN rol**, ni siquiera el dueño. El conteo a ciegas y la verificación sin sesgo valen para todos: la pantalla de captura no sabe de costos, sin importar quién la use.
- El **cocinero** nunca ve un costo en ninguna ruta — el estándar de tests que antes aplicaba a "operario" ahora aplica al rol cocinero, y las pantallas de captura se testean sin plata para todos los roles.
- En la base, los guards de rol (triggers de Backend #1 que exigen `role='owner'` para costos y órdenes) se extienden para aceptar también al admin — trabajo de Backend #2.

## Principios de diseño (no negociables)

Estas reglas mandan sobre cualquier decisión de implementación. Si algo las contradice, gana el principio.

### Principio rector

**Recoger bien el input y registrar bien la salida; el análisis es minería posterior.** El sistema de captura optimiza fidelidad y fricción cero en el momento del hecho (entrega verificada, foto del paquete, conteo). Todo cálculo, cruce o detección se hace después, sobre datos crudos bien registrados. Nunca sacrificamos calidad de captura por mostrar análisis en el momento.

### 1. Las pantallas de captura no saben de plata — y el cocinero no la ve NUNCA

Quien captura no ve análisis, totales, promedios, ni lo que el sistema "espera" que haya **fuera de la lista pre-cargada que está verificando**. En entrada, el default anunciado (cantidad) es parte del hecho a verificar, no un análisis. En inventario, se cuenta a ciegas: ver el número esperado invita a "cuadrar" en vez de contar.

**Reformulación 13 jul 2026 (roles)**: la plata vive en las **pantallas administrativas** (crear orden, historial de costos, tablero), accesibles a dueño y admin. Las **pantallas de captura** (verificar partida, contar, empacar) no muestran plata para ningún rol — ni siquiera el dueño. El **cocinero** no ve un costo en ninguna ruta del sistema. Verificable en tests: cualquier pantalla de captura que exponga costo, o cualquier ruta que exponga costo al rol cocinero, es un bug crítico.

### 2. Registrar un evento toma menos de 5 segundos

Tablet o celular, con las manos ocupadas o sucias. Botones grandes, mínimos toques, respuesta instantánea. Confirmar un producto que llegó como se anunció: un toque. La foto del pedido: sacar y seguir. Si un paso requiere más de 5 segundos o más de 3 toques, hay que rediseñar el flujo.

**En v0.3 aplica igual a partidas**: registrar una partida cuya cantidad matchea lo pendiente es un toque por producto. Sólo se tipea cuando difiere.

### 3. Nada se borra ni se edita sin rastro

Los usuarios son también potenciales auditados. Toda corrección es un **registro nuevo** que corrige uno anterior, nunca sobreescritura. Cada registro guarda quién, qué, cuándo, y — si corrige — a qué registro previo apunta. Editar un default en la verificación no pisa el valor anunciado: quedan ambos (anunciado vs. recibido).

**En v0.3 aplica igual a órdenes, partidas y costos**: cada partida es un registro nuevo con puntero a su orden. Cada corrección de costo es un registro nuevo con puntero al costo original. Cerrar una orden es un evento. Anularla es otro evento (que apunta al de cierre o directamente a la orden, según la decisión que tome el dueño arriba).

### 4. Productos como items independientes — **en la captura**

**En la captura**, cada producto sigue siendo una unidad atómica en su unidad natural: se compra, se cuenta y se registra como item independiente, sin composición.

**Ampliación v0.4**: en el **análisis** aparecen recetas y equivalencias — pero viven exclusivamente del lado del dueño y de la minería posterior. Si una pantalla de captura del operario necesita saber de qué está hecho algo, el diseño está mal.

## Requerimientos técnicos

- **Cámara del dispositivo:** la app necesita acceso a la cámara de la tablet/celular para las fotos de pedidos. Las fotos se suben asociadas al registro; si no hay conexión, quedan en cola local.
- **Moneda del negocio:** todos los costos se registran en **soles peruanos (PEN)**. Un solo valor, sin conversión ni multi-moneda en v0.3.

> **DECISIÓN RESUELTA (PR #95) — precisión decimal de costos: 2 decimales** (S/. 12.35).

## Convenciones técnicas del negocio

**Zona horaria del negocio**: la cocina opera en Perú → `America/Lima` (UTC-5, sin horario de verano). Todos los cortes de día — ventana de corrección del operario, "hoy" del tablero, filtros `from/to` — se calculan en esta zona horaria. Los timestamps siguen guardándose en UTC en la base; la zona horaria solo afecta la interpretación al agrupar por día calendario.

La zona horaria es **configurable** vía `COCINA_BUSINESS_TIMEZONE` (default `America/Lima`). Si el negocio se muda o abre otra cocina, se ajusta con env var — no requiere cambio de código ni migración.

---

## Fuera de alcance v0.4

Cada uno de estos ítems se convierte en un issue de GitHub cuando sea el momento. **No** entran a v0.4.

- **Registro de fabricación / producción de intermedios.** Descartado deliberadamente (decisión del dueño, 13 jul 2026): las recetas se aplanan al crudo y los preparados se resuelven por equivalencia en el conteo. Si algún día el negocio necesita trazabilidad de batches (lotes, vencimientos), se reevalúa.
- **Rentabilidad por plato.** Con recetas + costos ya casi existe; falta solo el precio de venta por plato. Un paso corto, pero fuera de v0.4.
- **Atribución de fuga por turno/operario.** La reconciliación de v0.4 es por producto y período. Cruzar discrepancias contra turnos es minería futura.
- **Integración automática con Rappi / PedidosYa.** El detalle del pedido se completa a mano. Después se conectan las APIs.
- **Reconocimiento de productos en la foto.** La foto es evidencia, no input estructurado. Minarla (OCR, visión) es análisis posterior, versión futura.
- **Múltiples cocinas.** El modelo de datos no debe cerrar la puerta a esto, pero la UI y la lógica asumen una sola cocina.
- **Multi-moneda.** Todos los costos en soles. Sin conversión ni proveedores en dólares.
- **Órdenes recurrentes / plantillas de orden.** Cada orden de compra se pre-carga a mano.
- **Alertas de "precio subió".** Detectar cambios de costo entre órdenes queda para el tablero avanzado, versión futura.

## Criterios de aceptación de v0.4

Sirve para saber cuándo v0.4 está terminada. Incluye todo lo de v0.2 y v0.3 (que siguen vigentes) más los agregados de v0.4.

### Heredados de v0.2 (siguen aplicando)

- [ ] El dueño puede pre-cargar una entrega (proveedor, productos, cantidades) — ahora bajo el concepto de **orden de compra** — y el operario la ve como **abierta** en su bandeja.
- [ ] Un operario puede validar una partida que llegó completa confirmando producto por producto con un toque cada uno (**siguiente/OK**), sin tipear cantidades.
- [ ] Un operario puede corregir la cantidad de un producto que llegó distinto al anunciado; quedan registrados el valor anunciado y el recibido.
- [ ] Al validar una partida, el stock se actualiza; antes, no.
- [ ] Un operario puede registrar la foto de un pedido en menos de 5 segundos y seguir trabajando (no bloqueante).
- [ ] Un pedido con foto queda **pendiente** en la bandeja; al completarlo con al menos 1 producto pasa a **terminado**; puede quedar solo-foto indefinidamente.
- [ ] Un operario puede registrar un conteo de inventario en menos de 5 segundos por producto.
- [ ] El operario nunca ve totales, consumos, ni comparativas (la lista pre-cargada de una entrega no cuenta como análisis).
- [ ] Toda corrección queda como un registro nuevo con referencia al original; el registro original no se modifica.
- [ ] El dueño ve, en su tablero, consumo por diferencia, stock actual y productos por acabarse — de un solo vistazo.
- [ ] El dueño puede reconstruir la trazabilidad completa de cualquier producto (todos los eventos que lo tocaron).

### Nuevos en v0.3 — plata

- [ ] El dueño puede registrar un costo unitario por cada ítem de una orden de compra al momento de comprar; el total se muestra calculado.
- [ ] **El operario nunca ve un costo, un precio, ni un total en plata en ninguna pantalla** — verificable con tests de UI y de API.
- [ ] El dueño ve en su tablero el **costo de inventario actual** (cuánta plata hay parada en depósito) y el **costo de consumo del período** (cuánta plata se consumió).
- [ ] Cada costo registrado queda con quién y cuándo lo cargó; las correcciones son registros nuevos con puntero al original.
- [ ] El costo de consumo y de inventario se valúan por FIFO por partidas (consumo agota partidas más viejas primero; inventario = suma de remanentes por partida), y el resultado es consistente y reproducible a mano.
- [ ] Las diferencias de conteo generan **ajustes de entrada** (sobrante, valuado al costo de la última partida) o **ajustes de salida** (faltante, agota partidas más viejas primero), como eventos append-only con quién/cuándo/motivo.

### Nuevos en v0.3 — partidas

- [ ] El dueño puede pre-cargar una orden de compra con productos y cantidades esperadas — igual que la "entrega" de v0.2 pero puede recibirse en varias tandas.
- [ ] Una orden de compra puede recibirse en **varias partidas**. Cada partida se valida con el mismo flujo del operario (bandeja → verificación → validar).
- [ ] Al validar cada partida, **el stock se actualiza con lo que llegó en esa partida** — no espera al cierre de la orden.
- [ ] La orden muestra saldo pendiente por producto entre partida y partida (ej: "faltan 40kg de pollo").
- [ ] La orden pasa a estado **cerrada** automáticamente al llegar todo, y el dueño puede reabrirla; ambos son eventos append-only.
- [ ] Los excesos quedan registrados como discrepancia visible al dueño; anular una orden conserva las partidas recibidas — cada camino queda como registro append-only.
- [ ] El tablero del dueño lista las órdenes con partidas parciales y muestra cuánto falta.

### Nuevos en v0.4 — catálogo y recetas

- [ ] Cada producto del catálogo declara su unidad natural, elegida de un catálogo de unidades cerrado; no existen variantes libres de texto ("Und/Unnd/Gram").
- [ ] El dueño puede definir y editar factores de conversión a gramos; cada cambio queda como registro nuevo y rige hacia adelante.
- [ ] Los 5 platos existen como productos tipo "plato" y son los que el operario usa al completar pedidos — sin ningún cambio en su flujo.
- [ ] El dueño puede definir la receta estimada de cada plato (insumos crudos + cantidades; packing según decisión); cada cambio crea una versión nueva sin recalcular teóricos pasados.
- [ ] Los preparados existen como productos contables con receta de equivalencia definida por el dueño, sin ningún registro de producción.
- [ ] **El operario no ve recetas, factores, equivalencias, teóricos ni discrepancias en ninguna ruta ni pantalla** — test automatizado obligatorio, mismo estándar que "no ve plata".

### Nuevos en v0.4 — reconciliación

- [ ] Tras cada conteo, el tablero muestra la discrepancia por producto (en unidad natural y en soles valuada por FIFO por partidas) del período entre conteos.
- [ ] Los preparados contados se convierten por equivalencia y acreditan sus crudos en la reconciliación — un batch a medio usar no aparece como fuga.
- [ ] El tablero rankea los productos por fuga en soles y marca en rojo los que superan el umbral definido (según decisión).
- [ ] Toda discrepancia es trazable: el dueño puede abrir un producto y ver los eventos que componen su teórico en el período.

## Próximos pasos

1. ~~El dueño revisa y contesta las decisiones~~ — **hecho**: las 8 de v0.3 (PR #95) y las 4 de v0.4 (PR #96) están incorporadas arriba como `DECISIÓN RESUELTA`.
2. **Construcción de v0.3 primero**: UX actualiza wireframes (orden de compra con costos, bandeja con órdenes abiertas y partidas parciales, tablero con plata); backend define el modelo append-only para orden de compra, partida y costo (migración incremental sobre v0.2); frontend implementa manteniendo el flujo de <5s del operario. Verificación: el operario no ve plata en ninguna ruta ni widget — test automatizado obligatorio.
3. **Después, v0.4 — carga inicial del catálogo** desde la planilla real: productos con su unidad natural, factores de conversión estimados, equivalencias de preparados, y las recetas de los 5 platos.
4. UX diseña las pantallas del dueño de v0.4: catálogo, editor de recetas/equivalencias, tablero de discrepancias. **Cero pantallas nuevas de operario** — criterio de diseño, no casualidad.
5. Backend define el modelo append-only para recetas versionadas, factores y equivalencias, y el cálculo de reconciliación como job de minería posterior.
6. Verificación end-to-end de v0.4: el operario no ve recetas ni discrepancias en ninguna ruta; una reconciliación de ejemplo se reproduce a mano y cuadra con la del sistema.
