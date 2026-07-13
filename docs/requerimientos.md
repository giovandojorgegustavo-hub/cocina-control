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

Las 8 decisiones abiertas de v0.3 fueron respondidas por el dueño en el PR #95: costo al comprar, cierre automático reabrible, el operario registra la partida, costo por unidad, valuación por **promedio ponderado**, exceso permitido y registrado como discrepancia, anular conserva las partidas recibidas, 2 decimales. v0.4 asume esas respuestas — en particular el promedio ponderado, que es la base para valuar las fugas en plata.

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

> **DECISIÓN DEL DUEÑO — momento del cargo del costo:**
> ¿El costo se anota al **momento de comprar** (cuando el dueño hace la orden al proveedor, antes de que llegue nada) o al **momento de recibir** (cuando el operario valida cada partida y el dueño confirma después)?
>
> Opciones:
> - **Al comprar**: rápido, el dueño lo carga una vez con la orden. Riesgo: si el precio final de la factura difiere (por ajustes del proveedor), hay que reabrir la orden para corregir.
> - **Al recibir**: refleja el precio real de cada partida (útil si el proveedor ajusta por peso o cambia precios entre tandas). Costo extra: el dueño tiene que entrar al sistema cada vez que llega una partida.
> - **Mixto**: el dueño carga estimado al comprar y corrige al recibir si difiere. Más flexible, más pantallas.

> **DECISIÓN DEL DUEÑO — granularidad del costo:**
> Cuando el dueño escribe el costo de un ítem de la orden, ¿lo hace **por unidad** (por kg, por unidad, por litro) o **total por ítem** (los 100kg de pollo costaron 850 soles)?
>
> Opciones:
> - **Por unidad**: fácil de reutilizar entre órdenes; el sistema calcula el total. Rompe cuando el proveedor cobra por lote (descuentos por cantidad).
> - **Total por ítem**: refleja la factura real; el sistema calcula el costo por unidad para reportes. Requiere que el dueño divida a mano si quiere reutilizar precios.

> **DECISIÓN DEL DUEÑO — método de valuación del consumo:**
> Cuando el mismo producto llegó a distinto costo (dos entregas de pollo con precios diferentes), ¿el consumo se valúa al costo de la **última partida** (LIFO), la **primera** (FIFO), o el **promedio ponderado** de lo que hay en stock?
>
> Opciones:
> - **FIFO** (primero en entrar, primero en salir): refleja la realidad culinaria (se usa lo más viejo primero). Requiere que el sistema recuerde el orden de las partidas.
> - **Promedio ponderado**: promedia los costos de todo el stock. Simple de calcular. Bueno cuando los precios varían poco.
> - **LIFO**: refleja el costo de reposición. Poco intuitivo para cocina.
> - Marcá cuál preferís por default; el dueño puede cambiarlo por producto si hace falta.

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

> **DECISIÓN DEL DUEÑO — cierre automático o manual:**
> ¿La orden se **cierra sola** cuando la suma de las partidas alcanza lo pedido, o la **cierra el dueño** manualmente aunque llegue todo?
>
> Opciones:
> - **Cierre automático**: menos fricción, no requiere acción del dueño. Cerró cuando el saldo por producto es 0.
> - **Cierre manual del dueño**: el dueño confirma que la orden está cerrada. Útil si a veces se aceptan pequeñas variaciones o si hay una revisión de factura antes de dar por cerrado.
> - **Cierre automático + posibilidad de reabrir**: cerró sola, pero el dueño puede reabrir si el proveedor manda algo más después.

> **DECISIÓN DEL DUEÑO — quién registra la partida:**
> ¿El **operario registra la partida** (como hoy con la verificación de entrada) o **solo el dueño** puede registrarla?
>
> Opciones:
> - **Operario**: mismo flujo que v0.2, se mantiene la velocidad y el operario no tiene que esperar al dueño. Consistente con "el operario anota lo que llegó".
> - **Sólo dueño**: si el dueño quiere ser el único autorizado a ampliar el stock. Rompe el flujo actual y bloquea al operario cuando el dueño no está.
> - **Operario registra, dueño valida después**: doble check, más fricción operativa.

> **DECISIÓN DEL DUEÑO — exceso de partida:**
> Si una partida llega con **más de lo que faltaba** para completar la orden (llegó 45kg cuando faltaban 40), ¿qué hace el sistema?
>
> Opciones:
> - **Aceptar el exceso**: se registra la partida completa, el sobrante entra al stock como excedente sobre la orden. Refleja la realidad; puede complicar la trazabilidad contra la factura.
> - **Rechazar el exceso**: solo se acepta hasta el máximo pendiente. El resto no queda registrado. Consistente con "la orden es lo que el dueño pidió" pero pierde stock real.
> - **Aceptar como orden nueva**: el sobrante se registra como una orden separada sin pre-carga. El dueño le pone el costo después.

> **DECISIÓN DEL DUEÑO — cancelación de orden con partidas ya recibidas:**
> ¿Se puede **anular una orden** que ya recibió una o más partidas? ¿Qué pasa con el stock que ya entró?
>
> Opciones:
> - **No se puede anular con partidas**: hay que cerrar y crear una orden nueva de "diferencia". Máxima trazabilidad.
> - **Anular es una corrección**: las partidas ya recibidas quedan como registros, la orden pasa a estado **anulada** con motivo. El stock ya no se toca (impacto histórico).
> - **Anular revierte el stock**: se descuentan las partidas del stock. Peligroso — puede dejar el stock negativo si ya se consumió algo.

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

- La discrepancia se reporta **por producto**, en unidad natural y en plata (valuada a promedio ponderado, la decisión de v0.3).
- El tablero del dueño muestra: discrepancia por producto del período, ranking de productos con mayor fuga en soles, y evolución entre conteos.
- **El operario no ve nada de esto.** Sigue contando a ciegas — el principio #1 es exactamente lo que hace confiable al conteo que alimenta este cálculo.
- Toda discrepancia es reconstruible: el dueño puede abrir un producto y ver los eventos que componen el teórico (conteo anterior, cada partida, cada pedido cuya receta usa ese insumo).

> **DECISIÓN RESUELTA (PR #96) — umbral de tolerancia: 5% de default global, ajustable por producto.**
> Ninguna cocina cuadra a cero: el umbral separa ruido normal (balanza, factores estimados) de "acá hay algo". El dueño puede ajustar el % por producto — el culantro merma distinto que los tenedores.

## Principios de diseño (no negociables)

Estas reglas mandan sobre cualquier decisión de implementación. Si algo las contradice, gana el principio.

### Principio rector

**Recoger bien el input y registrar bien la salida; el análisis es minería posterior.** El sistema de captura optimiza fidelidad y fricción cero en el momento del hecho (entrega verificada, foto del paquete, conteo). Todo cálculo, cruce o detección se hace después, sobre datos crudos bien registrados. Nunca sacrificamos calidad de captura por mostrar análisis en el momento.

### 1. El operario sólo verifica y anota — **y nunca ve plata**

Nunca ve análisis, totales, promedios, ni lo que el sistema "espera" que haya **fuera de la lista pre-cargada que está verificando**. En entrada, el default anunciado (cantidad) es parte del hecho a verificar, no un análisis. En inventario, sigue contando a ciegas: ver el número esperado invita a "cuadrar" en vez de contar.

**Ampliación v0.3**: **el operario tampoco ve plata**. Ni precio unitario, ni total, ni suma de partidas en costo. El costo vive del lado del dueño y no aparece en ninguna pantalla accesible al rol de operario. Verificable en tests: cualquier ruta o widget que exponga costo al operario es un bug crítico.

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

> **DECISIÓN DEL DUEÑO — precisión decimal de costos:**
> ¿Cuántos decimales tiene un costo? Opciones típicas: 2 decimales (S/. 12.35) o 4 decimales (S/. 12.3456) para casos donde el costo por unidad viene de dividir un total por una cantidad grande y el redondeo importa. Por default, 2 decimales.

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

- [ ] El dueño puede registrar un costo por cada ítem de una orden de compra (momento y granularidad exacta a definir en las decisiones del dueño arriba).
- [ ] **El operario nunca ve un costo, un precio, ni un total en plata en ninguna pantalla** — verificable con tests de UI y de API.
- [ ] El dueño ve en su tablero el **costo de inventario actual** (cuánta plata hay parada en depósito) y el **costo de consumo del período** (cuánta plata se consumió).
- [ ] Cada costo registrado queda con quién y cuándo lo cargó; las correcciones son registros nuevos con puntero al original.
- [ ] El tablero del dueño soporta cambiar el método de valuación del consumo (según decisión: FIFO / promedio ponderado / LIFO) y muestra el resultado consistente con ese método.

### Nuevos en v0.3 — partidas

- [ ] El dueño puede pre-cargar una orden de compra con productos y cantidades esperadas — igual que la "entrega" de v0.2 pero puede recibirse en varias tandas.
- [ ] Una orden de compra puede recibirse en **varias partidas**. Cada partida se valida con el mismo flujo del operario (bandeja → verificación → validar).
- [ ] Al validar cada partida, **el stock se actualiza con lo que llegó en esa partida** — no espera al cierre de la orden.
- [ ] La orden muestra saldo pendiente por producto entre partida y partida (ej: "faltan 40kg de pollo").
- [ ] La orden pasa a estado **cerrada** según la política elegida (cierre automático al llegar todo o cierre manual del dueño, según decisión arriba).
- [ ] Los excesos y las anulaciones se manejan según las decisiones del dueño de arriba — cada camino queda como registro append-only.
- [ ] El tablero del dueño lista las órdenes con partidas parciales y muestra cuánto falta.

### Nuevos en v0.4 — catálogo y recetas

- [ ] Cada producto del catálogo declara su unidad natural, elegida de un catálogo de unidades cerrado; no existen variantes libres de texto ("Und/Unnd/Gram").
- [ ] El dueño puede definir y editar factores de conversión a gramos; cada cambio queda como registro nuevo y rige hacia adelante.
- [ ] Los 5 platos existen como productos tipo "plato" y son los que el operario usa al completar pedidos — sin ningún cambio en su flujo.
- [ ] El dueño puede definir la receta estimada de cada plato (insumos crudos + cantidades; packing según decisión); cada cambio crea una versión nueva sin recalcular teóricos pasados.
- [ ] Los preparados existen como productos contables con receta de equivalencia definida por el dueño, sin ningún registro de producción.
- [ ] **El operario no ve recetas, factores, equivalencias, teóricos ni discrepancias en ninguna ruta ni pantalla** — test automatizado obligatorio, mismo estándar que "no ve plata".

### Nuevos en v0.4 — reconciliación

- [ ] Tras cada conteo, el tablero muestra la discrepancia por producto (en unidad natural y en soles a promedio ponderado) del período entre conteos.
- [ ] Los preparados contados se convierten por equivalencia y acreditan sus crudos en la reconciliación — un batch a medio usar no aparece como fuga.
- [ ] El tablero rankea los productos por fuga en soles y marca en rojo los que superan el umbral definido (según decisión).
- [ ] Toda discrepancia es trazable: el dueño puede abrir un producto y ver los eventos que componen su teórico en el período.

## Próximos pasos

1. ~~El dueño contesta las decisiones nuevas de v0.4~~ — **hecho**: las 4 fueron respondidas en el PR #96 y están incorporadas arriba como `DECISIÓN RESUELTA`.
2. Carga inicial del catálogo desde la planilla real: productos con su unidad natural, factores de conversión, equivalencias de preparados, y las recetas de los 5 platos.
3. UX diseña las pantallas del dueño: catálogo, editor de recetas/equivalencias, tablero de discrepancias. **Cero pantallas nuevas de operario** — criterio de diseño, no casualidad.
4. Backend define el modelo append-only para recetas versionadas, factores y equivalencias, y el cálculo de reconciliación como job de minería posterior.
5. Verificación end-to-end: el operario no ve plata ni recetas ni discrepancias en ninguna ruta; una reconciliación de ejemplo se reproduce a mano y cuadra con la del sistema.
