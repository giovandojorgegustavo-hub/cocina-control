# Requerimientos v0.2 — Cocina Control

Sistema para que el dueño de una dark kitchen detecte fugas de inventario sin cambiarle la vida al operario. En v0.2 capturamos hechos crudos con la mejor calidad de captura posible (qué llegó verificado contra lo anunciado, qué se empacó con foto, qué queda) y mostramos consumo por diferencia. La caza de fugas por receta queda para más adelante.

## Contexto

- **Negocio:** dark kitchen con 4 operarios part-time. Un operario por turno, cada uno trabaja 3 o 4 días por semana.
- **Problema:** el dueño sospecha fugas de inventario. El control es manual: llega una hoja con las compras, se confía que vino completo, cada tanto se cuenta lo que queda, y el dueño calcula consumos a mano restando inventarios.
- **Objetivo v0.2:** reemplazar la hoja de papel por un registro digital confiable y darle al dueño un tablero para ver consumo, stock y alertas. Sin fricción para el operario.

### Cambios respecto de v0.1

La revisión de los wireframes v0.1 con el dueño corrigió tres supuestos:

1. **Entrada no es carga libre, es verificación.** El dueño ya sabe qué compró: pre-carga la entrega esperada y el operario sólo la verifica.
2. **Pedido no es un toque, es una foto.** Lo que importa capturar del pedido es qué salió físicamente. La foto al empacar es el registro primario; el detalle de productos se completa después, sin bloquear el servicio.
3. **El inventario no es por turno.** Contar todo al cierre de cada turno es demasiada fricción. El conteo es periódico o cuando el dueño lo pide.

## Alcance v0.2

Tres registros de eventos y un tablero de lectura.

| Registro | Cuándo se usa | Qué se anota |
|---|---|---|
| **Entrada** | Llegó una entrega anunciada por el dueño | Verificación de la lista pre-cargada: qué llegó y cuánto |
| **Pedido** | Se empaca un pedido para despachar | Foto del paquete al momento; productos incluidos, después |
| **Inventario** | Periódico o a pedido del dueño | Cuánto queda de cada producto |

**Tablero del dueño** (sólo lectura, sólo dueño):

- Consumo por diferencia: `inventario anterior + entradas − inventario actual`
- Stock actual por producto
- Productos por acabarse

Los productos se manejan como items independientes. Sin recetas, sin platos compuestos en v0.2.

### Entrada — verificación contra lista pre-cargada

El dueño pre-carga cada entrega esperada (proveedor, productos, cantidades). Del lado del operario:

- **Bandeja de entregas** con estados: **no leído** → **validado**. Una entrega nueva aparece como no leída hasta que el operario la abre y la valida.
- Al abrir una entrega, el operario ve la lista pre-cargada con las **cantidades anunciadas como default editable**.
- **Flujo optimista:** si llegó lo anunciado, el operario confirma con **siguiente/OK** producto por producto sin tipear nada. Sólo tipea cuando la realidad difiere del default.
- **Al validar la entrega, impacta stock.** Antes de la validación, la entrega no afecta ningún número del sistema.

### Pedido — foto primero, no bloqueante

El registro primario del pedido es una **foto del paquete al momento de empacar**. El detalle viene después:

- **Foto al empacar:** el operario saca la foto y sigue trabajando. El registro queda en estado **pendiente** en la bandeja de pedidos.
- **Completar después:** cuando el servicio afloja, el operario abre el pedido pendiente y marca qué productos salieron (**mínimo 1 producto**). Al completarlo pasa a estado **terminado**.
- **Puede quedar solo-foto:** si nunca se completa, el registro vale igual como evidencia. El tablero lo muestra como pedido sin detalle.
- Nada del flujo bloquea el despacho: la foto toma segundos y el detalle es diferido.

### Inventario — periódico o a pedido

El conteo de stock (antes "cierre") **no está atado al turno**:

- Se cuenta **periódicamente** (frecuencia a definir con el dueño) o **cuando el dueño lo pide**.
- El flujo de conteo es el mismo que en v0.1: lista de productos, contar uno por uno, sin ver esperados.

> ⚠️ **Asunción a confirmar con el dueño:** la periodicidad concreta (¿semanal? ¿dos veces por semana? ¿sólo a pedido?) y quién dispara el conteo a pedido. El flujo de conteo se mantiene de v0.1 (renombrado a INVENTARIO en las pantallas); sólo la periodicidad y el aviso al operario quedan pendientes.

## Principios de diseño (no negociables)

Estas reglas mandan sobre cualquier decisión de implementación. Si algo las contradice, gana el principio.

### Principio rector

**Recoger bien el input y registrar bien la salida; el análisis es minería posterior.** El sistema de captura optimiza fidelidad y fricción cero en el momento del hecho (entrega verificada, foto del paquete, conteo). Todo cálculo, cruce o detección se hace después, sobre datos crudos bien registrados. Nunca sacrificamos calidad de captura por mostrar análisis en el momento.

### 1. El operario sólo verifica y anota

Nunca ve análisis, totales, promedios, ni lo que el sistema "espera" que haya **fuera de la lista pre-cargada que está verificando**. En entrada, el default anunciado es parte del hecho a verificar, no un análisis. En inventario, sigue contando a ciegas: ver el número esperado invita a "cuadrar" en vez de contar.

### 2. Registrar un evento toma menos de 5 segundos

Tablet o celular, con las manos ocupadas o sucias. Botones grandes, mínimos toques, respuesta instantánea. Confirmar un producto que llegó como se anunció: un toque. La foto del pedido: sacar y seguir. Si un paso requiere más de 5 segundos o más de 3 toques, hay que rediseñar el flujo.

### 3. Nada se borra ni se edita sin rastro

Los usuarios son también potenciales auditados. Toda corrección es un **registro nuevo** que corrige uno anterior, nunca sobreescritura. Cada registro guarda quién, qué, cuándo, y — si corrige — a qué registro previo apunta. Editar un default en la verificación no pisa el valor anunciado: quedan ambos (anunciado vs. recibido).

### 4. Productos como items independientes

Sin recetas, sin BOM, sin componentes. Cada producto se cuenta como una unidad atómica en v0.2. Esto se rompe deliberadamente en una versión futura (ver más abajo).

## Requerimientos técnicos

- **Cámara del dispositivo:** la app necesita acceso a la cámara de la tablet/celular para las fotos de pedidos. Las fotos se suben asociadas al registro; si no hay conexión, quedan en cola local.

## Convenciones técnicas del negocio

**Zona horaria del negocio**: la cocina opera en Perú → `America/Lima` (UTC-5, sin horario de verano). Todos los cortes de día — ventana de corrección del operario, "hoy" del tablero, filtros `from/to` — se calculan en esta zona horaria. Los timestamps siguen guardándose en UTC en la base; la zona horaria solo afecta la interpretación al agrupar por día calendario.

La zona horaria es **configurable** vía `COCINA_BUSINESS_TIMEZONE` (default `America/Lima`). Si el negocio se muda o abre otra cocina, se ajusta con env var — no requiere cambio de código ni migración.

---

## Fuera de alcance v0.2

Cada uno de estos ítems se convierte en un issue de GitHub cuando sea el momento. **No** entran a v0.2.

- **Recetas por plato.** Cruzar consumo esperado (ej: guacamole = 1 palta + 20g yogurt) contra consumo real medido. Es el detector de fugas real. Requiere que v0.2 esté estable y con datos limpios primero.
- **Integración automática con Rappi / PedidosYa.** En v0.2 el detalle del pedido se completa a mano. Después se conectan las APIs.
- **Reconocimiento de productos en la foto.** La foto es evidencia, no input estructurado. Minarla (OCR, visión) es análisis posterior, versión futura.
- **Múltiples cocinas.** El modelo de datos no debe cerrar la puerta a esto, pero la UI y la lógica de v0.2 asumen una sola cocina.

## Criterios de aceptación de v0.2

Sirve para saber cuándo v0.2 está terminada.

- [ ] El dueño puede pre-cargar una entrega (proveedor, productos, cantidades) y el operario la ve como **no leída** en su bandeja.
- [ ] Un operario puede validar una entrega que llegó completa confirmando producto por producto con un toque cada uno (**siguiente/OK**), sin tipear cantidades.
- [ ] Un operario puede corregir la cantidad de un producto que llegó distinto al anunciado; quedan registrados el valor anunciado y el recibido.
- [ ] Al validar la entrega, el stock se actualiza; antes, no.
- [ ] Un operario puede registrar la foto de un pedido en menos de 5 segundos y seguir trabajando (no bloqueante).
- [ ] Un pedido con foto queda **pendiente** en la bandeja; al completarlo con al menos 1 producto pasa a **terminado**; puede quedar solo-foto indefinidamente.
- [ ] Un operario puede registrar un conteo de inventario en menos de 5 segundos por producto.
- [ ] El operario nunca ve totales, consumos, ni comparativas (la lista pre-cargada de una entrega no cuenta como análisis).
- [ ] Toda corrección queda como un registro nuevo con referencia al original; el registro original no se modifica.
- [ ] El dueño ve, en su tablero, consumo por diferencia, stock actual y productos por acabarse — de un solo vistazo.
- [ ] El dueño puede reconstruir la trazabilidad completa de cualquier producto (todos los eventos que lo tocaron).

## Próximos pasos

1. UX actualiza los wireframes de entrada (bandeja + verificación) y pedido (foto → pendiente → terminado).
2. Confirmar con el dueño la periodicidad del inventario (asunción marcada arriba).
3. Backend define modelo de datos append-only para los tres registros, incluyendo entregas pre-cargadas y fotos.
4. Frontend implementa los flujos siguiendo las especificaciones de UX.
