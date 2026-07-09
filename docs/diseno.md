# Diseño técnico v0.1 — Cocina Control

## 1. Introducción

Este documento traduce los requerimientos de negocio y los wireframes de v0.2 en decisiones técnicas concretas: qué tecnología usar, cómo organizar la base de datos, y qué rutas de API expondrá el sistema.

**Quién lo lee:** el dueño de la cocina (para entender por qué se eligió cada cosa), el equipo de frontend (para consumir la API sin adivinar), y cualquier persona que entre al proyecto después.

**Cómo se conecta con los otros documentos:**
- `docs/requerimientos.md` — define QUÉ tiene que hacer el sistema y los cuatro principios no negociables. Este documento respeta esos principios sin excepción.
- `docs/ux/` — los wireframes definen cómo lo ve y usa cada usuario. Este documento define lo que hay detrás de cada pantalla.

Cada decisión técnica incluye una línea **"Qué significa en la práctica"** para que el dueño entienda la consecuencia real sin necesidad de saber programación.

---

## 2. Respuestas a las preguntas de los wireframes

### 2.a. Registro de entrada (`docs/ux/registro-entrada.md`)

**Pregunta 1:**
> ¿Una entrega anunciada puede editarse (el dueño) después de publicada? ¿Qué pasa si el operario ya la abrió?

**Respuesta:** Una entrega puede editarse mientras esté en estado `no_leida`. En cuanto el operario la abre, la entrega se marca `en_verificacion` y el dueño ya no puede modificarla. Al validarse, pasa a `validada` y se congela permanentemente. Si el dueño necesita corregir una entrega que el operario ya tiene abierta, debe comunicarse con él por fuera del sistema (esto es un caso raro; el flujo normal es que el dueño cargue la entrega antes del turno).

Técnicamente: la tabla `deliveries` tiene un campo `status` con tres valores posibles: `no_leida`, `en_verificacion`, `validada`. El endpoint de edición del dueño retorna error 409 (conflicto) si el status no es `no_leida`.

Qué significa en la práctica: una vez que el operario empezó a verificar, el dueño ya no puede cambiarle los números debajo de la mano. Si hay un error en lo anunciado, hay que resolverlo de persona a persona.

---

**Pregunta 2:**
> ¿Qué hace el operario si llegó un producto que NO está en la lista anunciada?

**Respuesta:** En v0.2 el operario no puede agregar productos a una entrega. La entrega es lo que el dueño declaró; si llegó algo extra, el operario avisa al dueño por fuera (por teléfono o mensaje). El dueño puede entonces editar la entrega si todavía está `no_leida`, o crear una segunda entrega con el ítem faltante. Si el escenario se repite con frecuencia, se diseña "agregar producto no anunciado" en v0.3.

Qué significa en la práctica: la pantalla del operario solo muestra los productos que el dueño cargó. No hay botón para agregar nada. Esto es intencional: evita que el operario registre cosas sin que el dueño las haya aprobado.

---

**Pregunta 3:**
> ¿Un producto puede llegar en cantidad 0 (no vino)?

**Respuesta:** Sí. El operario puede editar la cantidad a 0. El sistema guarda el par anunciado (por ejemplo, 10 kg) y recibido (0 kg). El stock no se toca para ese producto. No hay validación que rechace el 0; es un hecho válido — el proveedor no mandó ese ítem.

Qué significa en la práctica: si llegó la entrega pero le faltó un producto, queda registrado "anunciado: 10 kg, recibido: 0 kg". El dueño lo ve en el tablero y puede reclamar al proveedor con ese dato.

---

**Pregunta 4:**
> Si dos dispositivos validan la misma entrega offline, ¿quién gana?

**Respuesta:** Gana la primera validación que llega al servidor. El servidor verifica que el status de la entrega sea `en_verificacion` antes de aceptar la validación; si ya está `validada`, rechaza la segunda con un error claro ("esta entrega ya fue validada") y el dispositivo rezagado muestra un aviso al operario. La segunda validación se descarta completa — no se mezclan datos parciales.

Qué significa en la práctica: es un caso que casi nunca debería pasar (un turno, un operario, una tablet). Pero si pasa, el sistema no inventa datos mezclados: uno gana, el otro se entera.

---

**Pregunta 5:**
> ¿Cuál es la ventana en la que el operario puede corregir una entrega validada?

**Respuesta:** El operario puede crear registros de corrección mientras tenga sesión activa ese mismo día calendario. Pasada la medianoche, solo el dueño puede generar correcciones. La ventana se controla comparando el `created_at` de la sesión activa con la fecha del día en UTC-3 (zona horaria de Argentina).

Qué significa en la práctica: si Juan validó una entrega a las 14:00 y se dio cuenta del error a las 23:00 del mismo día, puede corregirlo solo. Si lo nota al día siguiente, tiene que pedirle al dueño que lo corrija.

---

### 2.b. Registro de pedido (`docs/ux/registro-pedido.md`)

**Pregunta 6:**
> ¿Registramos la plataforma (Rappi / PedidosYa) en algún momento del flujo?

**Respuesta:** No en v0.2. La plataforma queda fuera del camino crítico (foto) y también fuera del completar. El modelo de datos reserva un campo `platform` nullable en la tabla `delivery_orders` para no tener que migrar cuando se agregue. Si el dueño confirma que necesita el desglose antes de las integraciones por API, se agrega como selector opcional en "completar pedido" con un toque adicional — sin afectar el camino de la foto.

Decisión pendiente: confirmar con el dueño si necesita el campo plataforma antes de las integraciones. Si la respuesta es sí, se habilita el campo opcional en v0.2. Si la respuesta es no, queda para cuando se integren Rappi y PedidosYa por API.

Qué significa en la práctica: hoy el sistema no sabe si un pedido fue de Rappi o PedidosYa. No es un problema para v0.2 porque el análisis de fugas no depende de eso. Si el dueño lo necesita, se activa sin romper nada.

---

**Pregunta 7:**
> ¿Un operario puede completar un pedido que fotografió otro operario (turno anterior)?

**Respuesta:** Sí. El modelo guarda dos eventos separados: el evento de foto (con `photo_by` y `photo_at`) y el evento de completar (con `completed_by` y `completed_at`). Cualquier operario autenticado puede completar cualquier pedido pendiente. La trazabilidad queda completa: el dueño ve quién sacó la foto y quién llenó el detalle.

Qué significa en la práctica: si María sacó la foto a las 20:42 y Juan la completó a las 22:00 en el siguiente turno, quedan registrados ambos. Nadie puede borrar o reemplazar la autoría de la foto.

---

**Pregunta 8:**
> ¿Cuánto pesa la foto y cuánto se retiene?

**Respuesta:** El frontend comprime la foto en el dispositivo antes de subirla, con un techo de 800 KB por imagen (JPEG con calidad adaptativa). El servidor rechaza imágenes mayores a 2 MB como límite de seguridad. Formatos aceptados: JPEG y PNG. La retención mínima es de 90 días; después de ese período, las fotos pueden archivarse o eliminarse según lo que defina el dueño. Los registros de texto (metadatos del pedido) se retienen indefinidamente.

Decisión pendiente: confirmar con el dueño si 90 días es suficiente o si prefiere retención permanente. Depende del costo de almacenamiento que esté dispuesto a pagar.

Qué significa en la práctica: cada foto ocupa menos de 1 MB. Con 50 pedidos por día y 90 días de retención, son menos de 4 GB de fotos. Barato de guardar.

---

### 2.c. Registro de inventario (`docs/ux/registro-inventario.md`)

**Pregunta 9:**
> ¿El conteo exige contar TODOS los productos o puede ser parcial?

**Respuesta:** En v0.2, completo. El conteo no puede marcarse como terminado hasta que todos los productos activos del catálogo tengan un registro de conteo dentro de esa sesión. La única excepción: un producto puede contarse como 0 (explícito), pero no puede omitirse. Conteos parciales por categoría quedan para cuando existan categorías en el catálogo.

Qué significa en la práctica: si el catálogo tiene 15 productos, el operario no puede terminar el conteo habiendo anotado solo 12. El botón "terminar conteo" queda bloqueado hasta que los 15 tengan un valor.

---

**Pregunta 10:**
> ¿Una vez terminado el conteo, cuánto tiempo puede el operario seguir corrigiendo?

**Respuesta:** Igual que para las entregas: mientras la sesión esté activa ese mismo día calendario. Pasada la medianoche, solo el dueño puede generar correcciones. Toda corrección, dentro o fuera de esa ventana, es siempre un registro nuevo que apunta al original — nunca sobreescritura.

Qué significa en la práctica: si Juan contó 4 paltas y termina el conteo, pero después se da cuenta que eran 6, puede corregirlo ese mismo día. El sistema guarda los dos registros: el original (4) y la corrección (6), con la referencia entre ellos.

---

### 2.d. Tablero del dueño (`docs/ux/tablero-dueno.md`)

**Pregunta 11:**
> ¿Existe el concepto de rol (operario vs dueño) o hay una app distinta por rol?

**Respuesta:** Mismo sistema, distinto rol. La tabla `users` tiene un campo `role` con dos valores: `operator` y `owner`. El login es el mismo endpoint para ambos; la respuesta incluye el rol y el frontend redirige a la interfaz correcta. El backend rechaza con error 403 (prohibido) cualquier intento de un operario de acceder a rutas del tablero o a endpoints de administración.

Qué significa en la práctica: hay un solo sistema y un solo login. No hay dos apps que mantener. Si el dueño le da su usuario a un operario, es un problema de gestión de credenciales, no un hueco técnico — el sistema hace cumplir el rol en cada llamada al servidor.

---

**Pregunta 12:**
> ¿El umbral "por acabarse" es fijo, calculado por consumo promedio, o híbrido?

**Respuesta:** Fijo en v0.2. El dueño define un `low_stock_threshold` por producto al cargar el catálogo. Si el campo no tiene valor, el producto no aparece en el widget "por acabarse" pero sí aparece en la tabla general. No hay cálculo automático de umbral en v0.2.

Qué significa en la práctica: el dueño define una vez que, por ejemplo, cuando queden menos de 5 kg de pollo es momento de comprar. El sistema le avisa cuando el stock baja de ese número.

---

**Pregunta 13 (y al dueño):**
> v0.2 no captura la plataforma (Rappi / PedidosYa). ¿El dueño necesita el desglose antes de las integraciones por API?

**Respuesta:** Ver Pregunta 6. Esta misma decisión aplica acá — el campo está reservado en el modelo pero no se captura en v0.2 a menos que el dueño confirme que lo necesita. Se requiere confirmación del dueño antes de implementar.

---

**Pregunta 14:**
> La fórmula de consumo por diferencia necesita un "stock de inicio del período". ¿Se toma el último inventario anterior al inicio del rango, o el primero dentro del rango?

**Respuesta:** Se toma el último inventario registrado cuya fecha sea estrictamente anterior al inicio del rango seleccionado. Si no existe ningún inventario anterior al rango, la columna de consumo muestra "sin dato de inicio" y el cálculo queda vacío para ese producto. No se muestra un número si no hay base de comparación — un número inventado sería peor que ningún número.

La fórmula concreta: `consumo = stock_inicio + entradas_en_rango - stock_actual`, donde `stock_inicio` es el valor del último inventario anterior al rango y `stock_actual` es el valor del último inventario dentro o al cierre del rango.

Qué significa en la práctica: si el dueño elige "últimos 7 días" y el último conteo anterior a esos 7 días fue hace 10 días, ese conteo es el punto de partida. Si nunca hubo un conteo anterior, no hay con qué comparar y el sistema lo dice claro.

---

**Pregunta 15:**
> ¿Qué dispara el ícono de advertencia en la columna de consumo?

**Respuesta:** En v0.2, solo casos matemáticamente imposibles:
1. Consumo negativo: `stock_inicio + entradas < stock_actual` (el stock creció sin que haya entradas registradas).
2. Stock actual mayor que stock inicial más entradas del período (misma situación, imposible sin datos faltantes o incorrectos).

No se generan alertas por desviación de consumo esperado porque en v0.2 no hay recetas. Cuando el dueño vea un `⚠` en una fila, significa que los números no cierran matemáticamente — hay un dato faltante o una corrección que no se registró bien.

Qué significa en la práctica: el `⚠` no dice "se robaron algo". Dice "los números no cuadran, revisá los registros de ese producto". Es una señal de datos, no una acusación.

---

**Pregunta 16:**
> ¿El CSV debe mostrar correcciones como filas separadas (append-only) o el "estado final" reconciliado?

**Respuesta:** Append-only. El CSV exporta todas las filas tal como están en la base de datos, incluyendo los registros corregidos y las correcciones, con una columna `corrects_id` que indica a qué registro apunta cada corrección. Para entregas, incluye columnas `announced_qty` (cantidad anunciada) y `received_qty` (cantidad recibida). El dueño que quiera el estado final reconciliado puede filtrar en Excel tomando solo la última corrección de cada cadena.

Qué significa en la práctica: el CSV es la fuente forense completa. Muestra todo lo que pasó, no solo el resultado. Si hubo una corrección, se ven las dos filas: la original y la corrección. Nada desaparece.

---

## 3. Stack tecnológico

### 3.a. Propuesta por capa

| Capa | Tecnología elegida | Rol |
|---|---|---|
| Backend / API | FastAPI (Python) | Servidor que recibe las llamadas de la app y aplica la lógica de negocio |
| ORM y migraciones | SQLAlchemy 2 + Alembic | Mapeo de modelos a tablas y versionado de cambios de esquema |
| Validación | Pydantic v2 | Validación de inputs y serialización de respuestas |
| Base de datos | PostgreSQL | Almacena todos los registros de eventos, usuarios, productos |
| Almacenamiento de fotos | Filesystem local del droplet | Guarda los archivos de imagen de los pedidos en el servidor propio |
| Reverse proxy | Nginx | Termina HTTPS, sirve archivos estáticos (fotos), enruta tráfico al proceso FastAPI |
| Proceso en producción | systemd | Mantiene el proceso FastAPI corriendo y lo reinicia si falla |
| Hosting | Droplet DigitalOcean (propio del dueño) | Servidor dedicado bajo control total del dueño |
| Forma de servir la API | REST sobre HTTPS | Protocolo de comunicación entre la app y el servidor |
| Testing | pytest | Tests unitarios y de integración |
| Lint | ruff | Análisis estático y formateo de código Python |
| Gestión de dependencias | uv | Instalación y lockfile de paquetes Python |

### 3.b. Justificación por capa

**FastAPI (Python)**

FastAPI es el framework Python de mayor adopción para APIs REST en los últimos años. El dueño ya opera con este ecosistema; elegirlo significa que cualquier desarrollador que el dueño incorpore va a reconocer el código desde el primer día. FastAPI genera automáticamente documentación OpenAPI/Swagger disponible en `/docs` — el equipo de frontend puede ver todos los contratos de la API en vivo, sin documentación separada que se desactualice.

Alternativa descartada: Django + Django REST Framework (DRF). Django es un framework completo (ORM propio, admin, plantillas, autenticación integrada) diseñado para aplicaciones web tradicionales. Para una API pura, ese peso extra es una desventaja: más configuración inicial, más capas de abstracción, y una curva de entrada más alta para quien venga después. FastAPI hace exactamente lo que necesita este proyecto — servir una API JSON con validación fuerte y documentación automática — sin la superficie de Django que no se va a usar.

Qué significa en la práctica: el dueño (o quien contrate) puede incorporar un desarrollador Python sin necesidad de re-aprender el stack. La documentación de la API está disponible en el servidor en `/docs` sin trabajo adicional.

**SQLAlchemy 2 + Alembic**

SQLAlchemy 2 es el ORM estándar del ecosistema Python: define los modelos como clases Python y los traduce a SQL de forma predecible. Alembic es su compañero de migraciones — cada cambio de esquema queda versionado como un archivo en `migrations/`, se puede aplicar (`alembic upgrade head`) o revertir (`alembic downgrade`).

Qué significa en la práctica: ningún cambio de estructura de la base de datos se aplica a mano. Todo queda en código, en git, con historial. Si algo sale mal al desplegar, se revierte con un comando.

**Pydantic v2**

Valida los datos que entran por la API (tipos, formatos, longitudes) y serializa lo que sale. FastAPI lo usa internamente; el contrato de cada endpoint queda expresado como una clase Python que funciona como documentación ejecutable.

**PostgreSQL**

Base de datos relacional madura, con soporte nativo para transacciones (operaciones que se aplican completas o no se aplican). Eso es crítico para el modelo append-only: cuando el operario valida una entrega, el stock tiene que actualizarse en la misma operación que se guarda la validación — o ninguna de las dos. PostgreSQL garantiza eso.

Qué significa en la práctica: si el servidor se cae en el medio de una validación, la base de datos vuelve al estado anterior limpio. No quedan datos a medias.

**Nginx + systemd + droplet DigitalOcean**

El droplet es el servidor que ya opera el dueño: hardware dedicado, sin sorpresas de facturación por tráfico, sin límites de plan administrado. Nginx actúa como reverse proxy: recibe las conexiones HTTPS, termina el SSL, y reenvía las llamadas a la API al proceso FastAPI que corre internamente. También sirve las fotos como archivos estáticos (con validación de autenticación antes de cada archivo — ver sección 5). systemd es el administrador de procesos del sistema operativo Linux; se encarga de arrancar FastAPI al bootear el servidor y de reiniciarlo si falla.

Qué significa en la práctica: el servidor es infraestructura propia. El dueño no depende de ninguna plataforma gestionada. No hay facturación variable, no hay límites de plan, no hay vendor lock-in. Si algo falla, se conecta al droplet por SSH y se revisa directamente.

**REST sobre HTTPS**

REST (Representational State Transfer) es el estilo de API más utilizado y documentado. Cada acción tiene una URL y un método HTTP (GET para leer, POST para crear, etc.). Frontend lo consume con cualquier librería estándar. FastAPI genera la especificación OpenAPI automáticamente — el equipo de frontend accede a `/docs` para ver todos los endpoints, los campos requeridos, y los códigos de respuesta posibles, sin necesidad de un documento separado.

Qué significa en la práctica: la app del operario y el tablero del dueño hablan con el mismo servidor usando el mismo protocolo. La documentación de la API vive en el propio servidor y refleja el código real.

---

## 4. Modelo de datos append-only

### 4.a. Principio fundamental

Ninguna fila se actualiza ni se borra. Todo cambio es una fila nueva. Las tablas de eventos tienen:
- `id` — identificador único de cada registro.
- `created_at` — momento exacto en que se creó el registro (UTC).
- `created_by` — identificador del usuario que lo creó.
- `corrects_id` — referencia al registro que corrige (nulo si es un registro original).

### 4.b. Tablas

**users — Usuarios del sistema**

| Columna | Tipo | Descripción |
|---|---|---|
| id | UUID | Identificador único |
| name | TEXT | Nombre visible (Juan, María, etc.) |
| email | TEXT | Email de login, único |
| password_hash | TEXT | Contraseña hasheada con bcrypt |
| role | TEXT | `operator` o `owner` |
| created_at | TIMESTAMPTZ | Cuándo se creó la cuenta |

No es append-only: los usuarios se pueden modificar (cambiar contraseña, desactivar). Los eventos que el usuario generó sí son append-only y conservan el `created_by` original aunque el usuario se desactive.

---

**products — Catálogo de productos**

| Columna | Tipo | Descripción |
|---|---|---|
| id | UUID | Identificador único |
| name | TEXT | Nombre en mayúsculas (PALTA, POLLO, etc.) |
| unit | TEXT | Unidad de medida (`kg`, `un`, `lt`) |
| low_stock_threshold | NUMERIC | Umbral de stock bajo; nulo si no aplica |
| is_active | BOOLEAN | Falso si el producto se dejó de usar |
| created_at | TIMESTAMPTZ | Cuándo se creó |
| created_by | UUID | Usuario (dueño) que lo creó |

Los productos se desactivan (`is_active = false`), nunca se borran. El historial de eventos de un producto desactivado se conserva.

---

**deliveries — Entregas anunciadas (pre-cargadas por el dueño)**

| Columna | Tipo | Descripción |
|---|---|---|
| id | UUID | Identificador único |
| supplier_name | TEXT | Nombre del proveedor |
| status | TEXT | `no_leida`, `en_verificacion`, `validada` |
| created_at | TIMESTAMPTZ | Cuándo la cargó el dueño |
| created_by | UUID | Usuario (dueño) que la creó |
| validated_at | TIMESTAMPTZ | Cuándo la validó el operario; nulo si no |
| validated_by | UUID | Usuario (operario) que validó; nulo si no |

---

**delivery_items — Ítems de cada entrega (append-only)**

| Columna | Tipo | Descripción |
|---|---|---|
| id | UUID | Identificador único |
| delivery_id | UUID | Entrega a la que pertenece |
| product_id | UUID | Producto |
| announced_qty | NUMERIC | Cantidad que el dueño anunció |
| received_qty | NUMERIC | Cantidad que llegó realmente; nulo hasta que el operario confirma |
| created_at | TIMESTAMPTZ | Cuándo se registró este ítem |
| created_by | UUID | Quien lo registró |
| corrects_id | UUID | ID del delivery_item que corrige; nulo si es original |

Cuando el operario confirma una cantidad igual a la anunciada, `received_qty = announced_qty`. Cuando difiere, `received_qty` tiene el valor real. Cuando corrige, se crea una fila nueva con `corrects_id` apuntando a la fila anterior.

---

**delivery_orders — Pedidos de delivery (foto primero)**

| Columna | Tipo | Descripción |
|---|---|---|
| id | UUID | Identificador único |
| status | TEXT | `pending` (solo foto) o `completed` |
| photo_url | TEXT | Ruta del archivo de foto en el filesystem del droplet |
| photo_at | TIMESTAMPTZ | Momento en que se sacó la foto |
| photo_by | UUID | Operario que sacó la foto |
| completed_at | TIMESTAMPTZ | Momento en que se completó el detalle; nulo si no |
| completed_by | UUID | Operario que completó el detalle; nulo si no |
| platform | TEXT | Plataforma (Rappi, PedidosYa); nulo en v0.2 |
| created_at | TIMESTAMPTZ | Igual que photo_at en el caso normal |
| created_by | UUID | Igual que photo_by en el caso normal |
| corrects_id | UUID | Si este pedido anula uno anterior; nulo si es original |

---

**delivery_order_items — Productos declarados al completar un pedido**

| Columna | Tipo | Descripción |
|---|---|---|
| id | UUID | Identificador único |
| delivery_order_id | UUID | Pedido al que pertenece |
| product_id | UUID | Producto |
| quantity | NUMERIC | Cantidad declarada |
| created_at | TIMESTAMPTZ | Cuándo se completó |
| created_by | UUID | Operario que completó |
| corrects_id | UUID | Si corrige un detalle anterior; nulo si es original |

---

**inventory_counts — Sesiones de conteo de inventario**

| Columna | Tipo | Descripción |
|---|---|---|
| id | UUID | Identificador único |
| status | TEXT | `in_progress` o `completed` |
| started_at | TIMESTAMPTZ | Cuándo arrancó el conteo |
| started_by | UUID | Operario que lo inició |
| completed_at | TIMESTAMPTZ | Cuándo se terminó; nulo si sigue en progreso |
| completed_by | UUID | Puede ser distinto al que empezó; nulo si no terminó |
| created_at | TIMESTAMPTZ | Igual que started_at |
| created_by | UUID | Igual que started_by |

---

**inventory_count_items — Conteos individuales por producto (append-only)**

| Columna | Tipo | Descripción |
|---|---|---|
| id | UUID | Identificador único |
| inventory_count_id | UUID | Sesión de conteo a la que pertenece |
| product_id | UUID | Producto contado |
| quantity | NUMERIC | Cantidad contada |
| created_at | TIMESTAMPTZ | Cuándo se contó |
| created_by | UUID | Operario que contó |
| corrects_id | UUID | ID del item que corrige; nulo si es original |

### 4.c. Ejemplo concreto: corrección de un conteo

Juan cuenta 20 kg de papa y los anota. Unos minutos después se da cuenta que eran 18 kg.

Lo que pasa en la base de datos:

1. Fila original en `inventory_count_items`:
   - `id = A`, `product_id = papa`, `quantity = 20`, `created_by = Juan`, `corrects_id = null`

2. Juan toca "cambiar" en la pantalla. El sistema crea una fila nueva:
   - `id = B`, `product_id = papa`, `quantity = 18`, `created_by = Juan`, `corrects_id = A`

La fila `A` sigue en la base de datos, intacta. Nadie la tocó. El sistema sabe que la versión vigente de ese conteo es la fila `B` (la que tiene un `corrects_id` que apunta a `A`). Si el dueño descarga el CSV, ve las dos filas: la original y la corrección, con la referencia entre ellas.

### 4.d. Relaciones entre tablas (diagrama)

```
users
  |--- crea ---> deliveries
  |                  |--- contiene ---> delivery_items
  |                                         |--- puede corregir ---> delivery_item (corrects_id)
  |
  |--- fotografía --> delivery_orders
  |                       |--- contiene ---> delivery_order_items
  |                                              |--- puede corregir ---> delivery_order_item (corrects_id)
  |
  |--- inicia ---> inventory_counts
                       |--- contiene ---> inventory_count_items
                                              |--- puede corregir ---> inventory_count_item (corrects_id)

products <--- referenciado por delivery_items, delivery_order_items, inventory_count_items
```

---

## 5. Fotos de pedidos

### 5.a. Cómo se suben

El frontend comprime la foto en el dispositivo antes de enviarla (JPEG, calidad adaptativa, techo de 800 KB). La subida se hace directamente al backend en un único paso:

1. El frontend envía la foto al endpoint `POST /api/v1/delivery-orders/{id}/photo` como multipart/form-data.
2. El backend valida el JWT, guarda el archivo en el filesystem del droplet, y registra la ruta en la base de datos.

Límites:
- Tamaño máximo aceptado por el servidor: 2 MB (configurado en Nginx y validado en FastAPI).
- Formatos aceptados: JPEG y PNG.
- Si la subida falla (sin conexión), el frontend guarda la foto localmente y reintenta cuando vuelve la red. El registro del pedido ya existe en la base de datos; solo le falta la ruta de la foto.

### 5.b. Dónde se guardan

En el filesystem local del droplet, en la ruta `/var/lib/cocina-control/photos/{año}/{mes}/{uuid}.jpg`. El directorio no es público; Nginx no expone esa ruta directamente. Para acceder a una foto, la solicitud pasa primero por FastAPI, que valida el JWT y verifica que el usuario sea dueño o el operario que creó el pedido. Si la validación pasa, FastAPI responde con un header `X-Accel-Redirect` que le indica a Nginx que sirva el archivo internamente. El archivo nunca viaja dos veces por la red.

Qué significa en la práctica: nadie puede ver las fotos si no está logueado en el sistema. La URL de una foto no funciona sin un token válido. El servicio de las fotos no tiene costo variable — están en el mismo servidor que ya paga el dueño.

### 5.c. Cómo se sirven al dueño en el tablero

El tablero del dueño solicita la lista de pedidos. Cada pedido incluye la URL del endpoint de foto (`/api/v1/delivery-orders/{id}/photo`). El frontend la usa como `src` de la imagen; el navegador envía el JWT automáticamente y recibe el archivo. Si el dueño quiere ver la foto en tamaño completo, accede al mismo endpoint — no hay URL separada que expire.

Qué significa en la práctica: las fotos se cargan tan rápido como la conexión del droplet lo permita. No hay expiración de links ni necesidad de refrescar URLs.

### 5.d. Retención y backup

- Retención activa: 90 días mínimo (a confirmar con el dueño; ver Pregunta 8). Un job nocturno de cron elimina los archivos cuyo `created_at` supere el período configurado.
- Backup de fotos: rsync nocturno del directorio `/var/lib/cocina-control/photos/` a un segundo volumen del droplet o a un servicio externo de almacenamiento (DigitalOcean Spaces o similar). Como mínimo, el snapshot semanal del droplet cubre las fotos junto con todo lo demás.
- Los metadatos del pedido (quién, cuándo, qué productos) se retienen indefinidamente en PostgreSQL.
- Backup de la base de datos: `pg_dump` nocturno vía cron (ver sección 7).

---

## 6. Endpoints de la API

Todas las rutas tienen prefijo `/api/v1`. Toda llamada requiere header `Authorization: Bearer {token}` salvo el login. El backend retorna JSON siempre.

FastAPI genera automáticamente la especificación OpenAPI desde el código. La documentación interactiva está disponible en `/docs` (Swagger UI) y en `/redoc` (vista alternativa). El dueño o cualquier desarrollador puede explorar todos los endpoints, ver los campos requeridos y probar llamadas directamente desde el navegador, sin necesidad de un documento de API separado.

Códigos de error comunes:
- `400` — datos inválidos en el request.
- `401` — no hay token o es inválido.
- `403` — el rol no tiene permiso para esa ruta.
- `404` — el recurso no existe.
- `409` — conflicto de estado (por ejemplo, validar una entrega ya validada).

### 6.a. Autenticación

| Método | Path | Propósito | Input | Output | Quién |
|---|---|---|---|---|---|
| POST | `/auth/login` | Login de usuario | `{email, password}` | `{token, role, user_id}` | Todos |
| POST | `/auth/logout` | Invalidar sesión | — | `204` | Todos |

### 6.b. Productos (catálogo)

| Método | Path | Propósito | Input | Output | Quién |
|---|---|---|---|---|---|
| GET | `/products` | Listar productos activos | — | `[{id, name, unit, low_stock_threshold}]` | Todos |
| POST | `/products` | Crear producto | `{name, unit, low_stock_threshold?}` | `{id, name, unit}` | Dueño |
| PATCH | `/products/{id}` | Actualizar nombre, unidad o umbral | campos a cambiar | `{id, name, unit, ...}` | Dueño |
| DELETE | `/products/{id}` | Desactivar producto (no borra) | — | `204` | Dueño |

### 6.c. Entregas

| Método | Path | Propósito | Input | Output | Quién |
|---|---|---|---|---|---|
| GET | `/deliveries` | Bandeja de entregas | `?status=no_leida` (opcional) | `[{id, supplier, status, item_count, created_at}]` | Operario, Dueño |
| POST | `/deliveries` | Pre-cargar entrega | `{supplier_name, items: [{product_id, announced_qty}]}` | `{id, status, items}` | Dueño |
| GET | `/deliveries/{id}` | Detalle de una entrega | — | `{id, supplier, status, items: [{product_id, announced_qty, received_qty}]}` | Todos |
| PATCH | `/deliveries/{id}` | Editar entrega (solo si `no_leida`) | `{supplier_name?, items?}` | `{id, status}` | Dueño |
| POST | `/deliveries/{id}/open` | Marcar entrega como `en_verificacion` | — | `{id, status}` | Operario |
| POST | `/deliveries/{id}/items/{item_id}/confirm` | Confirmar ítem con cantidad recibida | `{received_qty}` | `{item_id, received_qty}` | Operario |
| POST | `/deliveries/{id}/validate` | Validar entrega completa e impactar stock | — | `{id, status, validated_at}` | Operario |
| POST | `/deliveries/{id}/items/{item_id}/correct` | Corregir cantidad de un ítem validado | `{received_qty, reason?}` | `{new_item_id, corrects_id}` | Operario (mismo día), Dueño |

### 6.d. Pedidos de delivery

| Método | Path | Propósito | Input | Output | Quién |
|---|---|---|---|---|---|
| GET | `/delivery-orders` | Bandeja de pedidos | `?status=pending` (opcional) | `[{id, status, photo_url, photo_at, photo_by}]` | Operario, Dueño |
| POST | `/delivery-orders` | Crear pedido (solo registro, sin foto aún) | — | `{id, status: pending}` | Operario |
| POST | `/delivery-orders/{id}/photo` | Subir foto del pedido | multipart/form-data (`file`) | `{id, photo_path, photo_at}` | Operario |
| POST | `/delivery-orders/{id}/complete` | Completar pedido con lista de productos | `{items: [{product_id, quantity}]}` | `{id, status: completed, items}` | Operario |
| POST | `/delivery-orders/{id}/cancel` | Anular un pedido pendiente | `{reason?}` | `{id, corrects_id}` | Operario, Dueño |
| POST | `/delivery-orders/{id}/correct` | Corregir productos de un pedido terminado | `{items: [{product_id, quantity}]}` | `{new_order_id, corrects_id}` | Operario, Dueño |

### 6.e. Inventario

| Método | Path | Propósito | Input | Output | Quién |
|---|---|---|---|---|---|
| POST | `/inventory-counts` | Iniciar un conteo | — | `{id, status: in_progress, started_at}` | Operario, Dueño |
| GET | `/inventory-counts/{id}` | Estado del conteo en progreso | — | `{id, status, items: [{product_id, quantity}]}` | Todos |
| POST | `/inventory-counts/{id}/items` | Registrar conteo de un producto | `{product_id, quantity}` | `{item_id, product_id, quantity}` | Operario |
| POST | `/inventory-counts/{id}/items/{item_id}/correct` | Corregir un conteo dentro de la sesión | `{quantity}` | `{new_item_id, corrects_id}` | Operario (mismo día), Dueño |
| POST | `/inventory-counts/{id}/complete` | Cerrar el conteo (requiere todos contados) | — | `{id, status: completed, completed_at}` | Operario |

### 6.f. Tablero del dueño

| Método | Path | Propósito | Input | Output | Quién |
|---|---|---|---|---|---|
| GET | `/dashboard/summary` | Vista principal: stock, consumo, alertas | `?from=&to=` | `{products: [{name, stock_now, entries, consumption, alert}], low_stock: [...], orders_summary: {completed, photo_only}}` | Dueño |
| GET | `/dashboard/traceability/{product_id}` | Todos los eventos de un producto | `?from=&to=` | `[{date, type, qty, operator, corrects_id}]` | Dueño |
| GET | `/dashboard/export` | Descargar CSV de eventos | `?from=&to=&type=all` | archivo CSV | Dueño |

---

## 7. Notas de implementación

### Operaciones en el droplet

**Backup de PostgreSQL**

Un job de cron ejecuta `pg_dump` cada noche y guarda el resultado comprimido en `/var/backups/cocina-control/`. El archivo tiene el timestamp en el nombre (`cocina-control_20260709_0300.sql.gz`). Se retienen los últimos 14 dumps. El backup se puede copiar también al segundo volumen del droplet o a DigitalOcean Spaces con rsync. Para restaurar: `pg_restore` apuntando al dump correspondiente.

**Backup de fotos**

rsync nocturno del directorio `/var/lib/cocina-control/photos/` al destino de backup configurado (segundo volumen o almacenamiento externo). El snapshot semanal del droplet actúa como red de seguridad adicional y cubre tanto la base de datos como las fotos en un mismo punto de restauración.

**Monitoreo mínimo**

- systemd reinicia el proceso FastAPI automáticamente si falla. El log queda en `journalctl -u cocina-control`.
- Nginx registra accesos y errores en `/var/log/nginx/`. Un cron de logrotate evita que crezcan indefinidamente.
- Para producción: configurar una alerta simple de uptime (UptimeRobot en plan gratuito o similar) que avise por email si el servidor no responde en más de 2 minutos.

**Despliegue**

El flujo de despliegue estándar es:

```bash
git pull origin main
uv pip install -r requirements.lock
alembic upgrade head
systemctl restart cocina-control
```

Opcionalmente, un `Makefile` con un target `deploy` encapsula estos pasos para ejecutar con un solo comando. No se requiere CI/CD en v0.2 — el despliegue manual por SSH es suficiente para el volumen de cambios esperado.

---

### Riesgos conocidos

**Sincronización offline.** El escenario crítico es el pedido: el operario saca la foto sin conexión, la foto queda en cola local, y mientras tanto otro operario podría estar mirando la bandeja. El riesgo es bajo (un solo operario por turno) pero existe. La solución en v0.2 es cola de reintentos en el cliente con `created_at` local como timestamp definitivo; el servidor acepta la foto cuando llega y no crea duplicados (idempotencia por `id` generado en el cliente).

**Conflicto de validación offline.** Cubierto en la Pregunta 4 — la primera validación gana, la segunda recibe un 409.

**Zona horaria.** Todos los timestamps se guardan en UTC en la base de datos. La conversión a hora local (UTC-3, Argentina) se hace en el cliente o en la capa de presentación del tablero. Esto evita problemas con el cambio de horario de verano (Argentina no lo usa, pero la práctica es correcta).

### Decisiones diferidas

- **Periodicidad del inventario y mecanismo de aviso al operario** — depende de confirmación del dueño (mencionado en `requerimientos.md` como asunción pendiente).
- **Campo `platform` en pedidos** — activar o no en v0.2 depende de la respuesta del dueño a la Pregunta 6 / Pregunta 13.
- **Política de retención de fotos más allá de 90 días** — decisión de costo que toma el dueño (Pregunta 8).
- **Panel de administración del dueño** (pre-carga de entregas, gestión de catálogo, trigger de conteo) — los wireframes lo mencionan pero no lo especifican. Se diseña aparte.

### Qué queda para v0.2

- Implementación de todos los endpoints listados en la sección 6.
- Migraciones de base de datos versionadas para cada tabla.
- Tests de integración para los flujos críticos: validación de entrega, conteo completo, flujo de foto.
- Documentación OpenAPI generada desde el código.

### Qué queda para versiones futuras

- Recetas y BOM (ingredientes por plato) — detector de fugas real.
- Integración automática con Rappi y PedidosYa por API.
- Conteos parciales por categoría.
- Múltiples cocinas.
- Reconocimiento automático de productos en la foto.
- Comparativas de comportamiento entre operarios.
