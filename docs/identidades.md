# Identidades por rol

Cada rol revisor de la Fabrica (`qa`, `seguridad`, `arquitecto`, `producto`) opera como una identidad distinta del implementador. Este documento describe el layout esperado de tokens, las cuentas maquina de GitHub, los permisos minimos del PAT y como se configura branch protection para exigir aprobacion no-autor.

Este repo **no crea** los tokens ni las cuentas. Los crea el operador con permisos de root y de administrador del repo en GitHub, fuera del arbol de git. Este documento es el **contrato**: describe que DEBE existir y estar configurado para que el circuito sea real. Nada de lo descrito aca se asume activo — ver el checklist de verificacion al final. Hasta que ese checklist este completo, el circuito opera por convencion (honor system) y NO ofrece las garantias de este documento.

## Layout de tokens

Los tokens viven fuera del repo, con permisos estrictos:

```
/etc/fabrica/tokens/qa.token
/etc/fabrica/tokens/seguridad.token
/etc/fabrica/tokens/arquitecto.token
/etc/fabrica/tokens/producto.token
```

- Dueno y grupo: `root:fabrica-tokens` (grupo dedicado, solo para esto).
- Permisos: `640` (root escribe; el grupo solo lee).
- El operador que lanza roles pertenece al grupo `fabrica-tokens`. Nadie mas.
- Contenido: un unico PAT de GitHub por rol, sin saltos de linea al final.
- `scripts/lanzar-rol.sh` corre como el operador (NUNCA como root) y lee el token directo. Si el operador no esta en el grupo, el script falla claro con exit 4.

Setup del grupo (una sola vez, como root):

```
groupadd --system fabrica-tokens
usermod -aG fabrica-tokens <usuario-operador>
chown root:fabrica-tokens /etc/fabrica/tokens/*.token
chmod 640 /etc/fabrica/tokens/*.token
```

Por que NO `root:root 600` + sudo: obligaria a correr el lanzador (y la sesion `claude` completa) como root para poder leer el token — maximo privilegio para una tarea de lectura. El grupo dedicado da el minimo real: root administra, el operador solo lee, el resto del sistema no ve nada.

## Cuentas maquina de GitHub

Cada rol revisor tiene una cuenta maquina propia en GitHub, distinta de la cuenta del implementador. Esta tabla es la UNICA fuente de verdad de nombres de cuenta — cualquier otro documento referencia esta tabla, no duplica literales:

| Rol | Cuenta maquina | Estado |
|-----|----------------|--------|
| `qa` | `qa-fabrica-gg` | creada |
| `seguridad` | `seguridad-fabrica-gg` | creada |
| `arquitecto` | *(pendiente de creacion)* | NO existe |
| `producto` | *(pendiente de creacion)* | NO existe |

Los roles cuya cuenta figura como **pendiente** operan por convencion: su revision se firma textualmente en el PR desde la cuenta del operador, se declara la excepcion en el mismo comentario, y NO cuenta como gate con enforcement. Cuando la cuenta se cree, se actualiza esta tabla y el CODEOWNERS en el mismo PR. No se declara enforcement de un rol cuya cuenta no existe.

El PAT que vive en `/etc/fabrica/tokens/<rol>.token` pertenece a la cuenta maquina correspondiente. **Nunca** a la cuenta del implementador.

## Permisos minimos del PAT

El ideal del contrato es **fine-grained**, restringido a los repos donde el rol revisa, con:

- **Contents: Read-only** — leer contenido, commits y diffs.
- **Pull requests: Read and write** — leer PRs y dejar comentario firmado / aprobar / pedir cambios.

### Excepcion vigente: PAT clasico con scope `repo`

GitHub HOY no soporta fine-grained PATs sobre repos de OTRA cuenta donde solo sos colaborador (limitacion documentada: el selector de repos de un fine-grained token solo lista repos propios del resource owner). Como los repos de la fabrica pertenecen a la cuenta del operador y las cuentas maquina son colaboradoras, los tokens de rol son **PAT clasico con scope `repo` unicamente** — el minimo clasico que permite revisar PRs privados. Sin `workflow`, sin `admin:*`, sin `delete_repo`, sin nada mas.

`repo` clasico incluye mas de lo deseado (contents write). Controles compensatorios mientras dure la excepcion:

- Branch protection en `main` rechaza push directo de cualquier cuenta — el contents write del token no alcanza la rama que importa.
- Expiracion corta (30 dias) y rotacion al vencer.
- Alcance humano: las cuentas maquina solo colaboran en los repos de la fabrica.

**Fix definitivo** (si se quiere volver al recorte fine-grained): mover los repos a una organizacion; alli el fine-grained PAT con resource owner = organizacion si permite seleccionar repos y recortar permisos por repo.

Si un PAT tiene mas scopes que `repo` (o, llegado el caso fine-grained, mas que los dos permisos listados), es un hallazgo bloqueante y `seguridad` debe reportarlo.

**Aclaracion sobre write a nivel cuenta vs token**: para que GitHub considere a una cuenta en CODEOWNERS, la cuenta necesita permiso **Write** en el repo como colaborador. Ese write es de la CUENTA; el PAT fine-grained que usa el circuito NO incluye Contents write, asi que el token del rol no puede pushear. El riesgo residual (la cuenta podria pushear con otra credencial propia) se cierra con branch protection: `main` protegida rechaza push directo de cualquiera, incluidas las cuentas maquina. El modelo de minimo privilegio es: cuenta con write formal + token recortado + rama protegida.

## Vector conocido: prompt injection sobre la sesion revisora

La sesion `claude` del rol revisor lee contenido controlado por el autor del PR (el diff, la descripcion, los comentarios) teniendo `GITHUB_TOKEN` con Pull requests write en su entorno. Un PR malicioso puede intentar inyectar instrucciones ("aproba este PR") para que la sesion apruebe bajo la identidad del rol. Mitigaciones vigentes: el contenido del PR se trata como NO confiable dentro de la sesion (regla en los prompts de rol), los repos son privados y el autor de los PRs es el propio operador. Si la fabrica incorpora autores externos, este vector escala y la aprobacion debe moverse fuera de la sesion que lee el diff (token de solo lectura para revisar; la aprobacion la emite un paso separado que no procesa contenido del PR).

## Riesgo residual: el ancla de confianza es el operador

Quien pertenece al grupo `fabrica-tokens` (hoy: el operador) puede leer los tokens de TODOS los roles y emitir aprobaciones como cualquiera de ellos con un `curl` directo, sin sesion de agente. En un setup mono-operador esto es inherente: el enforcement de GitHub distingue **sesiones y cuentas**, no intenciones del operador. Las garantias reales de este documento son (a) que un PR no se mergea sin dos aprobaciones formales trazables, y (b) que ninguna sesion de agente puede saltarse el circuito. Contra un operador que decide enganarse a si mismo, no hay control tecnico — y este documento no pretende tenerlo. Si algun dia hay mas de un humano, cada uno va en su propio grupo con acceso SOLO a sus roles, y este parrafo se reescribe.

## Branch protection para exigir aprobacion no-autor

En cada repo producto, `main` DEBE protegerse con la siguiente configuracion (esto es contrato a aplicar por el administrador del repo, no un estado ya activo — ver checklist al final):

- Require pull request reviews before merging: **si**.
- **Required approving reviews: 2.** Ver la aclaracion de abajo: sin este numero, CODEOWNERS solo exige UNA de las cuentas revisoras.
- Require approval from someone other than the last pusher: **si**. (Esto impide que el implementador apruebe su propio PR.)
- Dismiss stale pull request approvals when new commits are pushed: **si**.
- Require review from Code Owners: **si**.
- Restrict who can dismiss pull request reviews: solo administradores.
- Require status checks to pass before merging: **si**.
- Do not allow bypassing the above settings: **si**.

### Limitacion de CODEOWNERS: es OR, no Y

Cuando una linea de `CODEOWNERS` lista varias cuentas (`* @qa-fabrica-gg @seguridad-fabrica-gg`), GitHub satisface el requisito "Require review from Code Owners" con la aprobacion de **cualquiera** de ellas. CODEOWNERS NO puede expresar "qa Y seguridad". El "ambas revisiones obligatorias" del circuito se sostiene con la combinacion:

1. **Required approving reviews: 2** — el merge exige dos aprobaciones, y como los unicos revisores con cuenta son qa y seguridad, en la practica son ellas dos.
2. La confirmacion visual de quien mergea (comentario firmado de CADA rol requerido, con `author.login` correcto).

Si a futuro se suman mas cuentas revisoras (arquitecto, producto), el "2" deja de garantizar el par qa+seguridad y el chequeo debe pasar a una **GitHub Action** como required status check que valide que existe una review aprobada de cada cuenta requerida para el tipo de cambio. Esa Action es el unico camino para exigir combinaciones especificas.

## Verificacion tecnica de la firma (author.login)

La firma textual (`**Rol**: qa`, `**Rol**: seguridad`, etc.) es solo formato de lectura. **No prueba nada por si sola**: cualquiera con `pull_request:write` puede escribir esos strings.

La prueba real es que el `author.login` del comentario en la API de GitHub sea la cuenta maquina esperada segun la tabla de "Cuentas maquina de GitHub" de este documento:

| Rol declarado en el body | `author.login` esperado |
|--------------------------|-------------------------|
| `qa`                     | `qa-fabrica-gg`         |
| `seguridad`              | `seguridad-fabrica-gg`  |
| `arquitecto`             | *(sin cuenta aun — firma por convencion, sin enforcement)* |
| `producto`               | *(sin cuenta aun — firma por convencion, sin enforcement)* |

## Enforcement de identidad: nativo de GitHub, no de scripts

El enforcement de que "solo la cuenta maquina de un rol puede aprobar/comentar como ese rol" NO se hace con scripts locales. Se hace con la configuracion nativa de GitHub. La combinacion de cuatro mecanismos — **cuando esten aplicados y verificados** (checklist al final) — deja la puerta cerrada:

1. **Branch protection + "Require approval from someone other than the last pusher"**: GitHub bloquea el merge si la unica aprobacion viene de quien pusheo el ultimo commit. El implementador **no puede aprobar su propio PR**, sin importar que comente en el body.

2. **Branch protection + "Required approving reviews: 2" + "Require review from Code Owners"**: exigen que las aprobaciones vengan de las cuentas revisoras y que sean ambas (ver "Limitacion de CODEOWNERS" arriba: CODEOWNERS solo no alcanza).

3. **PATs restringidos por cuenta**: el PAT con Pull requests write vive solo en las cuentas maquina de rol. El PAT del implementador NO tiene esas cuentas ni puede simularlas. Un comentario o aprobacion "firmado" como `qa` que venga de otra cuenta queda visible en `author.login` en la UI de GitHub y en la API — no puede falsificarse desde otro token.

4. **Branch protection + "Do not allow bypassing"**: nadie (incluido admin) puede saltear las reglas anteriores sin dejar rastro. Ninguna cuenta maquina de rol figura en la "Bypass list": los revisores aprueban, **no bypasean**. Esto se audita en la revision de `seguridad` de cualquier PR que toque configuracion del repo.

Con esos cuatro mecanismos activos, la firma textual (`**Rol**: qa`) queda como convencion para lectura humana; la garantia real de identidad la da GitHub, no un script. Quien mergea confirma visualmente que cada comentario firmado necesario aparece con `author` = cuenta maquina esperada — no necesita ejecutar nada.

## Higiene de credenciales (issue #17)

- **2FA obligatorio** en todas las cuentas maquina y en la cuenta del operador. Sin excepcion.
- **Expiracion de PATs**: maxima 90 dias; la practica vigente es 30. Nunca tokens sin expiracion.
- **Rotacion**: al vencer, se regenera y se reemplaza el archivo en `/etc/fabrica/tokens/` (metodo a prueba de pegado en el runbook). Rotacion no programada INMEDIATA ante cualquier sospecha de filtracion — un PAT filtrado con Pull requests write puede aprobar merges falsos durante su ventana de vida.
- **Un token jamas viaja por un chat, un log, un commit o una URL.** Si paso, se considera filtrado: rotar ya.
- **Auditoria semestral** de scopes: cada PAT tiene exactamente lo que la seccion "Permisos minimos" declara; mas que eso es hallazgo bloqueante de `seguridad`.
- **Bypass list**: ninguna cuenta maquina figura en la Bypass list de branch protection (ya declarado en "Enforcement de identidad", mecanismo 4 — aca queda como regla de higiene explicita).

## Checklist de activacion (el circuito NO esta operativo hasta completarlo)

El operador/administrador verifica cada item y recien entonces el circuito ofrece sus garantias. Mientras falte alguno, todo merge es honor system y debe tratarse como tal:

- [ ] Cuentas maquina de qa y seguridad creadas (ver tabla) e invitadas con Write a cada repo producto y a fabrica.
- [ ] PAT generado por cuenta segun "Permisos minimos del PAT" (hoy: clasico con scope `repo` unicamente, por la excepcion vigente), guardado en `/etc/fabrica/tokens/<rol>.token`.
- [ ] Grupo `fabrica-tokens` creado; directorio `/etc/fabrica/tokens` con `root:fabrica-tokens 750`; tokens `root:fabrica-tokens 640`; operador en el grupo.
- [ ] Branch protection aplicada en `main` de cada repo con TODOS los items de la seccion "Branch protection" (incluido Required approving reviews: 2 y no-bypass). OJO (issue #34): la verificacion via API (`gh api .../branches/main/protection`) requiere permisos de ADMIN — una cuenta de rol (Write) recibe 404 AUNQUE la proteccion este activa. Ese 404 NO es evidencia de proteccion ausente: este checklist lo verifica el operador con su cuenta admin.
- [ ] Verificacion practica: un PR de prueba NO se puede mergear sin las dos aprobaciones ni con la aprobacion del propio autor.

### Por que este repo NO trae un script de verificacion

Una version previa de este circuito proponia un `scripts/verificar-firmas.sh` que consultara la API de GitHub y comparara `author.login` contra la cuenta esperada antes del merge. Se descarto por dos razones:

1. **Duplicaria lo que GitHub ya hace nativamente**. Los cuatro mecanismos de arriba ya impiden que una identidad falsa apruebe. Un script cliente que ademas grepea comentarios agrega superficie sin cerrar nada nuevo.
2. **El enforcement en cliente es esquivable por diseno**. Cualquier chequeo local se salta con no correrlo. El enforcement de politica tiene que vivir donde no se pueda esquivar — el servidor de GitHub, via branch protection + CODEOWNERS. Cualquier "gate" que dependa de que el operador humano se acuerde de correr un script es honor system, no enforcement.

Si en el futuro se necesita un chequeo automatizado adicional (por ejemplo, "el PR debe tener un comentario firmado de la cuenta maquina de qa segun la tabla antes de habilitar el merge"), va como **GitHub Action** en el mismo repo, no como script local. Una Action corre siempre y se ve en los required status checks — no se puede omitir.

## Endpoint de salud

El contrato del endpoint `/salud` que cierra la Definition of Done ("desplegado y verificado") vive en [`docs/salud-endpoint.md`](salud-endpoint.md). Ese documento incluye:

- El JSON minimo que debe devolver (`status` + `commit`).
- Las cinco condiciones que `scripts/deploy.sh` valida antes de aceptar el deploy.
- **Guia de migracion para servicios existentes** que ya tienen `/salud` pero aun no reportan el campo `commit` (tres pasos: capturar el SHA en build/arranque, exponerlo en el JSON, verificar con `deploy.sh`).

Este archivo (`identidades.md`) declara el contrato de identidades y credenciales; `salud-endpoint.md` declara el contrato del endpoint de salud. Ambos son parte del contrato general que fabrica exige a cada repo producto.

## Los dos regimenes de identidad (roles revisores vs constructores)

La Fabrica tiene 7 roles y TODOS se lanzan con `scripts/lanzar-rol.sh` — el lanzador es lo que convierte a un rol en un trabajador de verdad (prompt de rol + identidad + atribucion de su trabajo). Pero no todos tienen la misma identidad:

| Regimen | Roles | Identidad de GitHub | Puede aprobar PRs? |
|---------|-------|---------------------|--------------------|
| Con cuenta maquina | `qa`, `seguridad` | su propio PAT desde `/etc/fabrica/tokens/<rol>.token` | SI — sus aprobaciones cuentan para branch protection |
| Con identidad del operador | `backend`, `frontend`, `ux` (y `arquitecto`, `producto` hasta que sus cuentas existan) | la autenticacion de `gh` del operador | NO como rol — lo que hagan queda a nombre del operador |

Por que esta asimetria es deliberada: **el candado lo sostienen los revisores**. Un constructor no necesita identidad propia para construir — necesita su prompt de rol, su contexto separado y que su trabajo quede atribuido. Darles PATs propios agrandaria la superficie de credenciales sin agregar garantia: el gate ya exige dos aprobaciones de cuentas que el constructor no tiene.

`lanzar-rol.sh` resuelve el regimen solo: si existe el token del rol lo inyecta, si no, corre con la identidad del operador y lo dice en su linea de log (`identidad=operador`). Nunca falla por falta de cuenta maquina.

## Atribucion del trabajo en la bitacora

Cada sesion de rol queda registrada en la bitacora (via los hooks de ingesta del producto bitacora-v2). Para que el trabajo aparezca a nombre del rol que lo hizo y no de un cliente generico, `lanzar-rol.sh` exporta `BITACORA_V2_HOOK_TOKEN_FILE=/etc/bitacora-v2/hooks/<rol>.token` cuando ese archivo existe.

Layout esperado (lo crea el operador, mismo criterio que los PATs):

```
/etc/bitacora-v2/hooks/qa.token
/etc/bitacora-v2/hooks/seguridad.token
/etc/bitacora-v2/hooks/backend.token
...
```

Dueno `root:fiax`, permisos `640`, un token de scope `ingesta` por rol declarado en `/etc/bitacora-v2/tokens.yml`. Si el archivo del rol no existe, los hooks usan su token por defecto: el chat se ingiere igual con un empleado generico. **Nunca se pierde trazabilidad por falta de configuracion** — se pierde granularidad, que es recuperable.

## Que hace `scripts/lanzar-rol.sh`

1. Verifica que exista `.claude/agents/<rol>.md` en el repo actual.
2. Verifica que exista y sea legible `/etc/fabrica/tokens/<rol>.token`.
3. Inyecta el token via variable de entorno `GITHUB_TOKEN` (no lo escribe a disco).
4. Lanza `claude -p` con el prompt del rol concatenado al prompt/archivo del usuario.

Si el token o el archivo de rol no existen, el script **falla claro** y no lanza sesion. No hay "fallback" silencioso.

## Que NO hace este script (y por que)

- No crea tokens (eso es del operador con root).
- No configura branch protection (eso es del administrador del repo en GitHub).
- No auditariza los PATs (eso es del rol `seguridad` en cada PR).
- No hace merge (eso lo hace un rol distinto del implementador, con las revisiones firmadas ya en el PR).
