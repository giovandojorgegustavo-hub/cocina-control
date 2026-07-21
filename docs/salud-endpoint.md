# Contrato del endpoint de salud (`/salud`)

Este documento describe el contrato que cada repo producto DEBE cumplir para que `scripts/deploy.sh` pueda cerrar la Definition of Done ("desplegado y verificado"). El contrato tambien esta declarado sinteticamente en `CLAUDE.md`; aca queda la version larga y la **guia de migracion para servicios existentes**.

## Contrato

Cada repo producto expone un endpoint (por default `/salud`; puede vivir en otro path si el repo declara `HEALTH_URL` en `scripts/deploy.env`) que:

1. Responde HTTP **200** cuando la app esta lista para servir trafico.
2. Devuelve un cuerpo **JSON** con al menos estos dos campos:

```json
{
  "status": "ok",
  "commit": "<sha completo del commit que corre el proceso vivo>"
}
```

### `status`

- Solo `"ok"` cuenta como sano. Cualquier otro valor (`"degraded"`, `"starting"`, `"draining"`, etc.) es **app viva pero no lista**, y `scripts/deploy.sh` rechaza el deploy con exit != 0.
- La razon de tener el campo es distinguir "HTTP 200 vacio de contenido" (que curl considera OK) de "la app efectivamente esta lista". Sin este campo, un smoke test puede pasar con la DB caida.

### `commit`

- SHA completo (40 hex) del commit que el proceso vivo esta ejecutando, resuelto **en tiempo de arranque**.
- Se resuelve una sola vez, cuando arranca el proceso. No se recalcula por request.
- Fuentes tipicas para obtener el SHA en tiempo de arranque:
  - Variable de entorno inyectada por el build (`APP_COMMIT`, `GIT_SHA`, etc.).
  - `git rev-parse HEAD` ejecutado en el `WorkingDirectory` real del servicio al momento del start (no cacheado en el binario).
  - Un archivo de metadata embebido en el artefacto de despliegue (por ejemplo `dist/VERSION`).
- Sin este campo, `deploy.sh` no puede confirmar que el proceso vivo corre lo que se acaba de desplegar y **falla el deploy**. Esto cubre el caso de "systemd reinicio pero el `WorkingDirectory` apunta a otro checkout".

### Campos opcionales

El endpoint puede devolver mas campos (por ejemplo `deployed_at`, `db`, `queue_depth`). `deploy.sh` los ignora. La regla es: `status == "ok"` y `commit == commit desplegado` — con eso pasa. Todo lo demas es observability y no bloquea el deploy.

## Que valida `deploy.sh`

Del script en `scripts/deploy.sh`:

1. HTTP 200 en `HEALTH_URL` con `curl --fail` (`--max-time 10`).
2. `jq -r .status` == `"ok"`.
3. `jq -r .commit` == `git rev-parse HEAD` del checkout desplegado.
4. `systemctl show -p ActiveState` == `active`.
5. `ActiveEnterTimestamp` cambio antes/despues del restart (prueba que el proceso reinicio, no que se cacheo la respuesta anterior).

Si cualquiera de esas cinco falla, el deploy se rechaza y la feature NO cumple la DoD.

## Migracion para servicios existentes

Un servicio existente que ya tiene un endpoint `/salud` (o equivalente) pero **no reporta `commit`** cae en el contrato incumplido: `deploy.sh` lo va a rechazar en el paso 5 con exit code 8 ("`/salud` no reporta 'commit'; contrato del endpoint incumplido").

Este es el patch de migracion en tres pasos:

### Paso 1 — capturar el SHA en tiempo de build o arranque

Elegi una de estas segun el stack:

- **Contenedor / build reproducible**: pasa el SHA como `--build-arg GIT_SHA=$(git rev-parse HEAD)` y guardalo en una variable de entorno del proceso.
- **systemd unit sobre checkout**: agrega `Environment="APP_COMMIT=..."` con un `ExecStartPre=/usr/bin/git -C /opt/app rev-parse HEAD > /run/app/commit`, o resolvelo desde el proceso al arrancar leyendo `.git/HEAD` en el `WorkingDirectory`.
- **Binario compilado**: injecta el SHA como constante de link time (por ejemplo `-ldflags "-X main.commit=$SHA"` en Go).

Regla dura: el SHA se resuelve **una vez, al arranque**. No leer `.git/HEAD` por request (frag il, race con `git pull`, latencia).

### Paso 2 — exponerlo en `/salud`

Agregar el campo `commit` al JSON de respuesta. Ejemplo minimo (Python/Flask, pseudocodigo):

```python
APP_COMMIT = os.environ["APP_COMMIT"]  # falla al arrancar si falta

@app.get("/salud")
def salud():
    return {"status": "ok", "commit": APP_COMMIT}
```

Si el servicio ya tiene otros campos (`db`, `queue`, etc.), agregar `commit` al mismo JSON. No romper el shape existente.

### Paso 3 — verificar contra `deploy.sh`

Correr `scripts/deploy.sh` en el ambiente donde antes fallaba. La salida esperada termina en:

```
deploy: <servicio> activo desde <timestamp>, corriendo commit <sha> (confirmado por /salud).
deploy: OK.
```

Si el deploy sigue fallando con exit 9 ("el proceso vivo reporta commit X pero se desplego Y"), es porque el servicio efectivamente NO esta corriendo el checkout que `deploy.sh` cree. Ese es un bug real que el script esta cazando: el `WorkingDirectory` de la unit systemd probablemente apunta a otro path. Corregi la unit, no el contrato.

## Sudoers minimo para deploy.sh

`deploy.sh` ejecuta exactamente un comando con sudo: `sudo systemctl restart <SERVICE_NAME>`. La regla sudoers debe ser igual de exacta (issue #22) — un sudo amplio convierte cualquier compromiso del entorno del operador en root:

```
# /etc/sudoers.d/fabrica-deploy — una linea por servicio, unit EXACTA:
<operador> ALL=(root) NOPASSWD: /usr/bin/systemctl restart <service-name>.service
```

Sin comodines en el nombre de la unit, sin `systemctl *`, sin otros verbos. Si el operador ya tiene sudo general, esta regla no agrega nada — pero es el contrato correcto para hosts donde se quiera acotar.

## Que NO hace este endpoint

- No es un healthcheck de liveness para load balancers (aunque puede reutilizarse). Este endpoint sirve al circuito de deploy: verifica que "el commit que quise desplegar esta vivo". Un LB podria pedir un endpoint mas barato o mas frecuente.
- No expone datos sensibles: solo `status` y `commit`. El `commit` no es secreto (esta en GitHub).
- No requiere autenticacion. El endpoint se consulta desde el mismo host donde corre `deploy.sh` (o desde la red interna que ya tiene acceso al servicio).
