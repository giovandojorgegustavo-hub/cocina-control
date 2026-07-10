# Despliegue de cocina-control

Este documento describe cómo cocina-control corre en producción, cómo se hacen los releases,
cómo se rollbackea si algo sale mal, y cómo dejar el server preparado la primera vez.

## Topología

**Dominio**: `bonabowl.com` (existente, propiedad del sitio principal).
**Ruta**: `/interno` — subruta, no subdominio.

En el server de bonabowl corre **Caddy** que termina TLS y enruta:

| Path | Destino |
|---|---|
| `/` | El sitio principal de bonabowl (existente, fuera de este repo). |
| `/interno/api/*` | Reverse proxy a `http://127.0.0.1:8001` — el uvicorn del backend de cocina-control. |
| `/interno/*` (resto) | Archivos estáticos del bundle del frontend en `/opt/cocina-control/frontend-dist/` (valor `PROD_DEPLOY_PATH` sugerido; si cambiás la ruta, actualizá el Caddyfile también). |

Todo lo demás vive en el mismo server:

- **PostgreSQL 16** local, base `cocina_control_prod`, usuario `cocina`.
- **Fotos de pedidos**: filesystem en `/var/lib/cocina-control/photos/{año}/{mes}/{uuid}.jpg` (según diseño §5).
- **systemd unit** `cocina-control.service` que corre `uvicorn cocina_control.main:app --host 127.0.0.1 --port 8001`.
- **Env vars de producción** en `/etc/cocina-control/env` (fuera del deploy path — no se pisa con `rsync`).

## Cómo se hace un release

1. Localmente en tu máquina:
   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```
2. El workflow `.github/workflows/release.yml` se dispara. En orden:
   1. Job `tests` corre backend + frontend con el commit del tag.
   2. Job `build` genera el bundle con `VITE_BASE_PATH=/interno/` y lo sube como artifact.
   3. Job `deploy` espera **tu aprobación humana** — GitHub bloquea la ejecución hasta que
      apruebes en `Actions > release > Review deployments`. El environment se llama `produccion`
      y tiene required reviewer configurado.
3. Al aprobar, el runner conecta por SSH y ejecuta:
   1. `pg_dump` a `${DEPLOY_PATH}/backups/pre-${TAG}-${TIMESTAMP}.sql.gz`.
   2. `rsync -avz --delete` del código del tag (excluyendo lo que se genera en el server).
   3. `rsync` del bundle del frontend a `${DEPLOY_PATH}/frontend-dist/`.
   4. `uv sync --frozen`.
   5. `alembic upgrade head`.
   6. `sudo systemctl restart cocina-control.service`.
   7. `curl -sf http://127.0.0.1:8001/health` con 15 reintentos de 2 segundos.

Si cualquier paso falla, el run se marca en rojo. Ver "Rollback" abajo.

## Rollback

Cuando un release rompe algo en producción, hay dos vueltas atrás:

### 1. Rollback rápido: código anterior + restaurar el `pg_dump`

Requiere SSH al server como el usuario de deploy.

```bash
cd "${DEPLOY_PATH}"

# 1. Volver al tag anterior (código):
git fetch --tags
git checkout v0.0.9    # el tag previo que funcionaba
uv sync --frozen

# 2. Parar el servicio para que no haya writes durante el restore:
sudo systemctl stop cocina-control.service

# 3. Restaurar el pg_dump que se hizo ANTES de migrar el tag fallido:
#    El dump se toma con `--clean --if-exists`, así que el restore borra las
#    tablas actuales y las recrea. Esto funciona incluso si el deploy fallido
#    ya había corrido `alembic upgrade head` — el dump sabe cómo pisar el schema.
set -a; source /etc/cocina-control/env; set +a
DBURL="${COCINA_DATABASE_URL#postgresql+psycopg://}"
gunzip -c backups/pre-v0.1.0-*.sql.gz | psql "postgresql://${DBURL}"

# 4. IMPORTANTE: limpiar los secrets del entorno de la sesión antes de seguir.
#    `set -a; source ...` los exportó al shell; si se dejan vivos quedan
#    accesibles a cualquier subproceso durante toda la sesión SSH (y en
#    tmux/screen persisten hasta que se cierra la sesión de esos gestores).
unset COCINA_DATABASE_URL COCINA_JWT_SECRET COCINA_APP_ENV COCINA_PHOTOS_ROOT COCINA_BUSINESS_TIMEZONE

# 5. Reiniciar:
sudo systemctl start cocina-control.service

# 6. Verificar:
curl -sf http://127.0.0.1:8001/health && echo "OK"
```

**Prerrequisitos**:
- El `git checkout` asume que `${DEPLOY_PATH}` es un clon git. Ver "Bootstrap del server" para inicializarlo así.
- Si el rollback te asusta, corré primero `sudo -iu cocina bash -lc 'cd /opt/cocina-control && uv run alembic current'` para saber en qué revisión de schema está la base y decidir si conviene el rollback rápido o el lento.

### 2. Rollback lento: rehacer un release al tag anterior

Si preferís usar el mismo pipeline y saltarte el paso manual:

1. Empujá un tag nuevo apuntando al commit del tag previo:
   ```bash
   git tag v0.1.1 v0.0.9
   git push origin v0.1.1
   ```
2. Aprobá el deploy en GitHub. El robot corre el mismo flujo, hace un pg_dump nuevo,
   despliega el código anterior, y aplica `alembic upgrade head` — que si es idempotente
   contra el schema actual, no hace nada.

**Ojo**: alembic downgrade automático NO forma parte del pipeline por diseño (el downgrade
en producción está BLOQUEADO en `env.py`). El único camino para bajar el schema es restaurar
un `pg_dump` anterior.

## Snippet de Caddy para `/interno`

En el Caddyfile del server, dentro del bloque `bonabowl.com { ... }`, agregar:

```caddy
bonabowl.com {
    # ... resto del sitio principal arriba ...

    # ===== cocina-control bajo /interno =====

    # 1. La API: /interno/api/* → backend en 127.0.0.1:8001.
    # handle_path strippea /interno del path antes de proxear, así el backend
    # recibe /api/v1/... exactamente como lo espera (montado en /api/v1 en main.py).
    handle_path /interno* {
        # Sólo requests que empiezan con /interno/api/ pasan al backend.
        @api path /api/*
        reverse_proxy @api 127.0.0.1:8001 {
            header_up X-Forwarded-For {remote_host}
            header_up X-Forwarded-Proto {scheme}
            header_up X-Forwarded-Host {host}
        }

        # Cualquier otra ruta bajo /interno/ es archivo estático del bundle.
        root * /opt/cocina-control/frontend-dist
        try_files {path} /index.html
        file_server

        # Cachear assets versionados agresivamente (Vite los hashea).
        @hashedAssets path /assets/*
        header @hashedAssets Cache-Control "public, max-age=31536000, immutable"

        # NO cachear el shell, el manifest y el service worker — invalidan al deployar.
        @noCache path /index.html /manifest.webmanifest /sw.js /registerSW.js
        header @noCache Cache-Control "no-cache, must-revalidate"
    }

    # ... resto del sitio principal abajo ...
}
```

Después de editar el Caddyfile:
```bash
sudo caddy fmt --overwrite /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

## Env vars de producción (en `/etc/cocina-control/env`)

Este archivo lo lee el systemd unit y también los pasos SSH del release. NO se commitea, NO se rsynca — vive fuera del deploy path.

```bash
COCINA_DATABASE_URL=postgresql+psycopg://cocina:PASSWORD@127.0.0.1:5432/cocina_control_prod
COCINA_JWT_SECRET=<64-char hex — generar con: python -c "import secrets; print(secrets.token_hex(32))">
COCINA_APP_ENV=prod
COCINA_PHOTOS_ROOT=/var/lib/cocina-control/photos
COCINA_BUSINESS_TIMEZONE=America/Lima
```

Permisos:
```bash
sudo chmod 600 /etc/cocina-control/env
sudo chown cocina:cocina /etc/cocina-control/env
```

## Bootstrap del server (una vez)

Antes del primer deploy, dejar el server preparado. Todo se hace SSH-eado como root o con `sudo`.

### 1. Usuario del sistema

```bash
sudo useradd -m -s /bin/bash cocina
```

### 2. Instalar `uv` como el usuario

```bash
sudo -iu cocina bash -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'
```

Verificar: `sudo -iu cocina uv --version`.

### 3. PostgreSQL

Instalar PostgreSQL 16, crear rol y base:

```sql
CREATE ROLE cocina LOGIN PASSWORD '<generar-otro-secret>';
CREATE DATABASE cocina_control_prod OWNER cocina;
```

### 4. Ruta de fotos

```bash
sudo mkdir -p /var/lib/cocina-control/photos
sudo chown cocina:cocina /var/lib/cocina-control/photos
```

### 5. Ruta de deploy con clon inicial

```bash
sudo mkdir -p /opt/cocina-control
sudo chown cocina:cocina /opt/cocina-control
sudo -iu cocina bash -c 'cd /opt/cocina-control && git clone https://github.com/giovandojorgegustavo-hub/cocina-control.git .'
sudo -iu cocina bash -c 'cd /opt/cocina-control && mkdir -p backups frontend-dist'
```

Este clon es lo que permite el rollback rápido con `git checkout`. El robot de despacho hace `rsync --delete` que preserva `.git/` (está en el exclude).

**Si el repo pasa a ser privado**: el clone anónimo por HTTPS falla. Dos alternativas:
- Clonar por SSH con una deploy key: `ssh-keygen -t ed25519 -f ~/.ssh/repo_readonly -N "" -C "readonly@bonabowl"`, agregar `~/.ssh/repo_readonly.pub` como **Deploy Key con acceso de sólo lectura** en el repo de GitHub, y clonar con `git clone git@github.com:giovandojorgegustavo-hub/cocina-control.git .` desde el usuario `cocina`.
- O crear un Personal Access Token con scope `repo:read` y clonar con `https://<TOKEN>@github.com/...` (el token queda en `.git/config`; permisos 600).

### 6. Archivo de env vars

Crear `/etc/cocina-control/env` con el contenido de arriba. Permisos 600.

### 7. systemd unit

Crear `/etc/systemd/system/cocina-control.service`:

```ini
[Unit]
Description=cocina-control backend
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=cocina
Group=cocina
WorkingDirectory=/opt/cocina-control
EnvironmentFile=/etc/cocina-control/env
ExecStart=/home/cocina/.local/bin/uv run uvicorn cocina_control.main:app --host 127.0.0.1 --port 8001
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Habilitar y arrancar:
```bash
sudo systemctl daemon-reload
sudo systemctl enable cocina-control.service
sudo systemctl start cocina-control.service
```

### 8. Sudoers para el deploy user

Crear `/etc/sudoers.d/cocina-control-deploy`:

```
cocina ALL=(root) NOPASSWD: /bin/systemctl restart cocina-control.service, /bin/systemctl status cocina-control.service, /bin/systemctl status cocina-control.service --no-pager, /bin/systemctl stop cocina-control.service, /bin/systemctl start cocina-control.service
```

`chmod 440`. Reglas mínimas — sólo lo que el deploy necesita. Notá que `--no-pager` está explícito porque el workflow lo usa así (`sudo /bin/systemctl status cocina-control.service --no-pager`), y sudoers matchea el comando **completo** con sus argumentos: sin la línea con `--no-pager` el paso "Report failure" del release fallaría con "sudo: command not allowed".

### 9. Llave SSH para el deploy user

En el server:
```bash
sudo -iu cocina bash -c 'mkdir -p ~/.ssh && chmod 700 ~/.ssh && ssh-keygen -t ed25519 -f ~/.ssh/deploy_key -N "" -C "cocina-control@github-actions"'
```

- La llave **pública** (`~/.ssh/deploy_key.pub`) va a `~/.ssh/authorized_keys` del mismo usuario.
- La llave **privada** (`~/.ssh/deploy_key`) se copia al secret `PROD_SSH_PRIVATE_KEY` del environment `produccion` en GitHub (ver la sección "Secrets" abajo).

### 10. Host key para pinneo desde GitHub

En cualquier máquina confiable con acceso al server:
```bash
ssh-keyscan -H bonabowl.com
```

La salida completa (o al menos las líneas de tipo ed25519 y rsa) se copia al secret
`PROD_SSH_HOST_KEY` del environment `produccion`. Esto fija la identidad del server:
un cambio de key rompe el deploy adrede.

### 11. Caddy

Agregar el bloque `/interno` del snippet de arriba al Caddyfile. Reload.

## Secrets del environment `produccion`

En GitHub: **Settings > Environments > New environment `produccion`** con:

- **Required reviewers**: @giovandojorgegustavo-hub (o quien apruebe los deploys).
- **Deployment branches**: sólo tags que matchean `v*`.
- **Secrets**:

| Nombre | Valor |
|---|---|
| `PROD_SSH_HOST` | Hostname o IP del server. |
| `PROD_SSH_USER` | Usuario de deploy (`cocina`). |
| `PROD_SSH_PRIVATE_KEY` | Contenido completo de `~cocina/.ssh/deploy_key` en el server. |
| `PROD_SSH_HOST_KEY` | Salida de `ssh-keyscan -H <host>` obtenida desde red confiable. |
| `PROD_DEPLOY_PATH` | Ruta absoluta del deploy en el server (`/opt/cocina-control`). |

## Qué NO cachea Caddy

El bundle de Vite hashea nombres de archivos de `/assets/*.js` y `/assets/*.css` — se cachean 1 año.
Los que NO se hashean y por eso NO se cachean:

- `/index.html` — apunta a los assets hasheados; cambia en cada deploy.
- `/manifest.webmanifest` — la config de la PWA.
- `/sw.js` y `/registerSW.js` — el service worker.

Sin este `Cache-Control: no-cache`, un release rompería la PWA porque el navegador serviría un `index.html` viejo que apunta a assets que ya no existen.

## Riesgos conocidos

- **Rollback de código lento por clon git**: si el server no tiene `.git/` (bootstrap saltado), el rollback con `git checkout` falla. El pg_dump siempre existe; el rollback "vuelta atrás" alternativo (empujar un tag apuntando al commit previo) sigue funcionando.
- **Un solo entorno**: no hay staging. Las mitigaciones son (a) tests contra el commit del tag antes del deploy, (b) required reviewer para el deploy, (c) pg_dump antes de migrar. Cuando el proyecto crezca, agregar un `staging` con el mismo pipeline es directo.
- **BACKEND_PORT hardcodeado**: el puerto `8001` está en el YAML del workflow (no en secrets). Si algún día tiene que cambiar, se edita en el workflow y en el Caddyfile.

## Verificación end-to-end tras un release

1. `curl -sfI https://bonabowl.com/interno/` → 200 OK, `Content-Type: text/html`.
2. `curl -sf https://bonabowl.com/interno/manifest.webmanifest | jq .name` → `"Cocina Control"`.
3. Login como dueño desde el navegador — sesión inicia, redirige a `/interno/tablero`.
4. En el server: `sudo journalctl -u cocina-control -n 50 --no-pager` sin errores nuevos.
