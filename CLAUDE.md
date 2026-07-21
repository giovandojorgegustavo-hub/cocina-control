# Reglas de la Fabrica

## Proceso
- Todo cambio nace en una rama, nunca directo en main.
- Mensajes de commit: formato convencional (tipo: descripcion).
- Antes de commitear: git status y git diff, siempre.

## Estructura
- src/ codigo, tests/ pruebas, migrations/ cambios de BD, docs/ decisiones.
- docs/adr/ para ADRs de arquitectura. docs/ux/ para especificaciones de flujo. docs/producto/ para criterios de aceptacion.

## Contexto de producto
- Cada repo producto DEBE tener `.claude/contexto-producto.md` con: quien es el usuario, en que dispositivo, en que condiciones, que valora, y que restricciones tiene.
- Todo rol lee ese archivo ANTES de actuar. Si no existe, el rol PARA y reporta hallazgo bloqueante.
- Los roles de la Fabrica son genericos: no contienen contexto de producto. El contexto lo pone el repo.

## Contratos: una sola fuente de verdad
- El rol `arquitecto` es dueño UNICO de los NOMBRES de contrato: campos, endpoints, eventos, codigos de error. El contrato vive en UN solo documento (el del arquitecto).
- Ningun otro artefacto de planificacion transcribe esos nombres. La spec de UX y los criterios de producto los REFERENCIAN por seccion ("el buscador, ver contrato §4") y describen la PANTALLA y el comportamiento observable.
- Corolario: cuando el arquitecto renombra algo, cambia UN archivo. Es imposible que UX quede desincronizada porque nunca tuvo copia propia.
- Para qa: nombres tecnicos transcritos fuera del contrato son UNA violacion de proceso (se reporta esta regla), no N hallazgos de desincronizacion a corregir string por string.
- Origen: cuatro rondas de revision del plan de bitacora-v2 rebanada 2 gastadas en "UX dice X, el contrato dice Y" (issue #46). DRY aplicado a los artefactos de planificacion.

## Roles
- Los archivos de rol viven en `.claude/agents/`: backend, frontend, ux, qa, seguridad, arquitecto, producto.
- Un rol solo actua si esta invocado explicitamente. No hay revision "implicita".
- Un rol puede delegar en sub-agentes si el trabajo lo amerita, pero **responde por el resultado**: su respuesta final es el entregable o su resumen sustantivo, jamas un aviso de que delego. La sesion del rol es lo que queda registrado; una traza vacia con un costo al lado no es trazabilidad.
- **Prohibicion dura: quien implementa un PR NO puede ejecutar ni redactar sus propias revisiones qa o seguridad.** Cada revision es una sesion separada del implementador.
- Cada revision (qa, seguridad, arquitecto, producto) deja **comentario firmado** en el PR con: nombre del rol, timestamp, hash del commit revisado, y veredicto. **Sin comentario en el PR, la revision no existio.**

## Pull Requests
- Todo merge a main pasa por Pull Request en GitHub.
- El PR muestra el diff completo: se lee ANTES de aprobar.
- **Todo PR referencia su issue en el body** (`Closes #N` para el que cierra el trabajo, `Refs #N` para avances parciales — las palabras clave son en INGLES, GitHub no entiende "Cierra"). Es como el vigilante resuelve que issue etiquetar (ADR 002 §3); un PR sin issue referenciado es violacion de proceso que qa señala en su revision.
- **PRs encadenados**: antes de mergear el PR padre con borrado de rama, reapuntar los hijos a main (gh pr edit <hijo> --base main). GitHub CIERRA (no retargetea) un PR cuya rama base se borra, y un PR cerrado con base borrada no puede reabrirse — hay que crear uno nuevo y re-revisar (leccion del issue #28).

## Estados de un trabajo (ADR 002)
- La fuente de verdad del estado de un trabajo son los labels `estado:*` del ISSUE: `pendiente → en-curso → fallo-1/fallo-2 → bloqueada`; terminada = issue cerrado, sin label. Los escriben el vigilante y el lanzador; el tablero de Projects es SOLO una vista — si tablero y labels difieren, ganan los labels.
- `bloqueada` requiere operador. Al re-etiquetar `pendiente`, se remueven los `fallo-*` y el contador de reintentos arranca de cero: la intervencion humana resetea el historial.
- Cada corrida de un rol tiene su `run_id` (lo genera lanzar-rol) y queda en la linea `run:` del comentario firmado. Eventos JSONL, clasificacion de fallos transitorios y politica de reintentos: ADR 002 y `docs/vigilante.md`.

## Ordenes multi-operario (issue padre + sub-issues, ADR 002 §6)
- Una orden que requiere varios roles es un **issue padre**: contiene los artefactos de las estaciones tempranas (requerimientos destilados, links a mockups). NO contiene la implementacion.
- El rol `arquitecto` comenta su plan en el padre y lo parte en **sub-issues** (funcion nativa de GitHub; ya habilitada en el repo), uno por rol ejecutor. Cada sub-issue nace con el label `rol:<rol>` y vive su ciclo completo issue → rama → PR con su propio estado y assignee.
- El `arquitecto` queda como assignee del padre hasta su cierre: es el responsable del conjunto.
- El padre cierra cuando cierran todos los hijos. Un hijo `bloqueada` NO propaga al padre automaticamente: el padre refleja progreso, no estado agregado — el operador ve el bloqueo en el hijo y decide.
- Fallback si sub-issues no estuviera disponible en un repo: task-list de issues linkeados en el cuerpo del padre (`- [ ] #N`).

## Circuito de revision (cableado por evento)
- **Todo PR de codigo**: recibe revision de `qa` Y `seguridad`, como sesiones separadas del implementador, con comentario firmado en el PR.
- **Cambio de UI**: exige spec de `ux` ANTES del codigo, y aceptacion de `producto` DESPUES del codigo (reproducida desde la pantalla del usuario, sobre datos reales, no seeds).
- **Cambio estructural** (esquema, contratos entre modulos, dependencias nuevas, acoplamiento): exige revision de `arquitecto`.
- Hallazgos criticos o altos bloquean el merge hasta ser resueltos.
- Hallazgos medios y bajos se registran como issues en GitHub y no bloquean.
- El enforcement de identidad de los revisores es nativo de GitHub: branch protection (con required approving reviews: 2) + CODEOWNERS + "Require approval from someone other than the last pusher" + PATs con Pull requests write solo en las cuentas maquina de rol. El implementador no puede aprobar su propio PR ni simular ser otra cuenta. La tabla de cuentas por rol (unica fuente de verdad de nombres) y el checklist de activacion viven en `docs/identidades.md` — el enforcement rige recien cuando ese checklist esta completo.
- Antes de mergear, quien mergea confirma visualmente en el PR que cada revision necesaria dejo comentario firmado desde su cuenta maquina esperada segun la tabla de `docs/identidades.md` (por ejemplo, revision de `qa` debe venir de `author = qa-fabrica-gg`). No hay script local que reemplace esto: el gate real es el de GitHub. Si un comentario firmado viene de otra cuenta, NO se mergea.
- Si los checks estan verdes, todas las revisiones necesarias tienen comentario firmado desde su cuenta maquina, y no hay hallazgos bloqueantes: **el merge lo ejecuta el operador**. Los PATs de rol no tienen contents write a proposito — ningun trabajador puede mergear. La garantia de no-autoaprobacion no depende de quien aprieta el boton: la da branch protection (2 aprobaciones + no-bypass).

## Definition of Done
Una feature esta terminada cuando:
1. El PR esta mergeado en main.
2. El codigo esta **desplegado** en el ambiente vivo (proceso corriendo el commit nuevo).
3. Esta **verificada ahi**: smoke test contra el endpoint de salud + verificacion de que el proceso vivo corre el commit desplegado.

Mergeado NO es desplegado. Desplegado NO es verificado. El paso obligatorio es `scripts/deploy.sh`.

### Contrato del endpoint de salud
Cada repo producto expone `/salud` (o el path que declare `HEALTH_URL`) devolviendo HTTP 200 y JSON con al menos:

```json
{ "status": "ok", "commit": "<sha completo del commit que corre el proceso vivo>" }
```

- `status`: solo `"ok"` cuenta como sano. Cualquier otro valor (`"degraded"`, `"starting"`, etc.) es app viva pero no lista, y `scripts/deploy.sh` rechaza el deploy.
- `commit`: sha completo del commit que el proceso esta ejecutando, resuelto en tiempo de arranque (ej: variable de build o `git rev-parse HEAD` embebido). Sin este campo, `deploy.sh` no puede confirmar que el proceso vivo corre lo que se acaba de desplegar y falla.

Este contrato es lo que separa "systemd reinicio algo" de "el commit desplegado esta vivo".

Version larga del contrato, checklist de las cinco validaciones que corre `deploy.sh`, y **guia de migracion para servicios existentes que aun no reportan `commit`** en `docs/salud-endpoint.md`.

## E2E por UI real
Los tests de interfaz DEBEN ejercitar la UI real contra la app viva, nunca solo seeds de base. Un flujo que solo pasa con seeds no cuenta como cubierto. La herramienta concreta (Playwright u otra) la declara cada repo producto en su `contexto-producto.md` — el proceso exige el QUE, el producto elige el CON QUE.

## Operaciones como codigo
- `scripts/deploy.sh` es el paso obligatorio del DoD. Cada repo producto lo parametriza via `scripts/deploy.env`: git pull --ff-only, migraciones si corresponde, restart del servicio declarado, smoke test que exige `status=ok` en el body de `/salud`, y confirmacion final de que el commit reportado por `/salud` coincide con el commit desplegado.
- `scripts/lanzar-rol.sh` es el mini-lanzador de identidades: recibe rol y prompt/archivo, lanza una sesion claude con el rol y el token correspondiente. Ver `docs/identidades.md` para el layout de tokens y la configuracion de branch protection.
- `scripts/sincronizar-desde-fabrica.sh` es el mecanismo canonico de propagacion. Fabrica NO publica tags: cada repo producto declara en `FABRICA_VERSION` el commit SHA (40 hex) de fabrica que consume. El script descarga el tarball de ese SHA, copia SOLO los archivos declarados en su allowlist explicita (nunca directorios, nunca `rm -rf`), y NUNCA toca `docs/adr/`, `.claude/contexto-producto.md` ni archivos propios del repo producto. Cada actualizacion se abre como PR y pasa por qa + seguridad. Detalle y racional en `docs/adr/001-sync-fabrica-a-repos-producto.md` DEL REPO FABRICA — los ADRs de fabrica NO se propagan por el sync a proposito: `docs/adr/` de cada repo producto pertenece al producto (issue #33).
