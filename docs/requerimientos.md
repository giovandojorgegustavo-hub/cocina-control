# Requerimientos v0.3 — Cocina Control

Sistema para que el dueño de una dark kitchen detecte fugas de inventario sin cambiarle la vida al operario. En v0.2 capturamos hechos crudos (qué llegó verificado, qué se empacó con foto, qué queda) y mostramos consumo por diferencia en cantidades. En v0.3 sumamos dos capacidades para que el dueño pueda tomar decisiones con datos completos: **saber cuánto le cuesta el inventario y el consumo**, y **registrar entregas que llegan en varias tandas**. La caza de fugas por receta sigue post-v0.3.

## Contexto

- **Negocio:** dark kitchen con 4 operarios part-time en Lima. Un operario por turno, cada uno trabaja 3 o 4 días por semana.
- **Problema:** el dueño sospecha fugas de inventario. El control es manual: llega una hoja con las compras, se confía que vino completo, cada tanto se cuenta lo que queda, y el dueño calcula consumos a mano restando inventarios.
- **Objetivo v0.3:** consolidar v0.2 con **plata** (costos por lado del dueño) y **partidas** (una orden puede recibirse en varias tandas). Ambos requerimientos vienen de la operación real de las últimas semanas: proveedores que entregan fraccionado y decisiones de compra que hoy se toman sin ver el costo de lo que se está consumiendo.

### Cambios respecto de v0.2

v0.2 asumía dos cosas que la operación real desmintió:

1. **Una entrega = una llegada.** Los proveedores entregan **fraccionado**: la orden de 100kg de pollo llega como 30 el lunes, 40 el martes, 30 el jueves. Hoy el operario tiene que decidir si valida "lo que llegó hasta ahora" o esperar a que se complete — cualquiera de las dos rompe la trazabilidad. v0.3 acepta explícitamente **recepciones por partidas**: cada tanda se pesa y registra por separado, sumando hasta cerrar la orden.
2. **El sistema no habla de plata.** El dueño mide cantidades y calcula "cuánto me costó" a mano, en Excel. Los pedidos grandes se deciden sin ver el costo de lo que ya está en stock ni el costo del consumo del período. v0.3 agrega **costos del lado del dueño** (el operario nunca ve plata, ni siquiera de reojo). Habilita costo de inventario y costo de consumo — cálculos posteriores, no en el momento de captura.

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

Los productos siguen siendo items independientes. Sin recetas, sin platos compuestos en v0.3.

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

### 4. Productos como items independientes

Sin recetas, sin BOM, sin componentes. Cada producto se cuenta como una unidad atómica en v0.3. Esto se rompe deliberadamente en una versión futura (ver más abajo).

## Requerimientos técnicos

- **Cámara del dispositivo:** la app necesita acceso a la cámara de la tablet/celular para las fotos de pedidos. Las fotos se suben asociadas al registro; si no hay conexión, quedan en cola local.
- **Moneda del negocio:** todos los costos se registran en **soles peruanos (PEN)**. Un solo valor, sin conversión ni multi-moneda en v0.3.

> **DECISIÓN DEL DUEÑO — precisión decimal de costos:**
> ¿Cuántos decimales tiene un costo? Opciones típicas: 2 decimales (S/. 12.35) o 4 decimales (S/. 12.3456) para casos donde el costo por unidad viene de dividir un total por una cantidad grande y el redondeo importa. Por default, 2 decimales.

## Convenciones técnicas del negocio

**Zona horaria del negocio**: la cocina opera en Perú → `America/Lima` (UTC-5, sin horario de verano). Todos los cortes de día — ventana de corrección del operario, "hoy" del tablero, filtros `from/to` — se calculan en esta zona horaria. Los timestamps siguen guardándose en UTC en la base; la zona horaria solo afecta la interpretación al agrupar por día calendario.

La zona horaria es **configurable** vía `COCINA_BUSINESS_TIMEZONE` (default `America/Lima`). Si el negocio se muda o abre otra cocina, se ajusta con env var — no requiere cambio de código ni migración.

---

## Fuera de alcance v0.3

Cada uno de estos ítems se convierte en un issue de GitHub cuando sea el momento. **No** entran a v0.3.

- **Recetas por plato.** Cruzar consumo esperado (ej: guacamole = 1 palta + 20g yogurt) contra consumo real medido. Es el detector de fugas real. Requiere que v0.3 esté estable y con datos limpios primero.
- **Integración automática con Rappi / PedidosYa.** En v0.3 el detalle del pedido se completa a mano. Después se conectan las APIs.
- **Reconocimiento de productos en la foto.** La foto es evidencia, no input estructurado. Minarla (OCR, visión) es análisis posterior, versión futura.
- **Múltiples cocinas.** El modelo de datos no debe cerrar la puerta a esto, pero la UI y la lógica de v0.3 asumen una sola cocina.
- **Rentabilidad por plato.** Combinar recetas + costos daría rentabilidad. Depende de que existan recetas — post-v0.3.
- **Multi-moneda.** Todos los costos en soles. Sin conversión ni proveedores en dólares en v0.3.
- **Órdenes recurrentes / plantillas de orden.** Cada orden de compra se pre-carga a mano en v0.3.
- **Alertas de "precio subió".** Detectar cambios de costo entre órdenes queda para el tablero avanzado, versión futura.

## Criterios de aceptación de v0.3

Sirve para saber cuándo v0.3 está terminada. Incluye todo lo de v0.2 (que sigue vigente) más los agregados de v0.3.

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

## Próximos pasos

1. El dueño revisa este documento y contesta cada `> DECISIÓN DEL DUEÑO:` antes de que UX arranque wireframes v0.3.
2. UX actualiza los wireframes: nueva pantalla de orden de compra con costos (dueño), bandeja del operario ahora con órdenes abiertas y partidas parciales, tablero enriquecido con costo de inventario / consumo.
3. Backend define el modelo de datos append-only para orden de compra, partida y costo. Migración incremental sobre v0.2 (sin migración destructiva).
4. Frontend implementa los flujos siguiendo las especificaciones de UX. El operario mantiene su flujo de <5s por evento.
5. Verificación end-to-end: el operario no ve plata en ninguna ruta ni en ningún widget. Test automatizado obligatorio.
