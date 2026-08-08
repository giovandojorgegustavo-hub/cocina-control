#!/usr/bin/env bash
# scripts/deploy.sh — despliega el commit actual al ambiente vivo y verifica.
#
# Uso:
#   scripts/deploy.sh
#
# Configuracion por repo en scripts/deploy.env (NO versionado):
#   SERVICE_NAME=<systemd unit>           # ej: bitacora-api
#   HEALTH_URL=<url del smoke test>       # ej: http://10.14.0.1:8000/salud
#   MIGRATIONS_CMD=<comando o vacio>      # ej: python3 scripts/migrar.py
#   BRANCH=<rama viva>                    # default: main
#   HEALTH_DEADLINE=<segundos>            # default: 60 (polling del smoke test)
#
# Contrato de deploy.env (issue #22): dueno = el operador (o root), permisos
# SIN escritura para otros (600/640/644 estan bien; 662/666 NO). Este script
# lo verifica antes de source-arlo: un deploy.env escribible por cualquiera
# es ejecucion de codigo con los privilegios (y el sudo) del operador.
# MIGRATIONS_CMD se ejecuta SIN shell (sin pipes ni redirecciones): si la
# migracion necesita shell, envolvela en un script versionado del repo.
#
# sudo minimo requerido: ver "Sudoers minimo" en docs/salud-endpoint.md
# (NOPASSWD solo para systemctl restart de la unit declarada, nada mas).
#
# Contrato del endpoint de salud (obligatorio para el DoD):
#   HTTP 200 + JSON con al menos { "status": "ok", "commit": "<sha completo>" }.
#   - "status" != "ok" -> app degradada -> el deploy falla aunque HTTP sea 200.
#   - "commit" != commit desplegado -> el proceso vivo corre otro codigo ->
#     el deploy falla. Esto cubre el caso de "systemd reinicio pero el
#     WorkingDirectory apunta al checkout viejo".
#
# Dependencias: jq (para leer el JSON de salud sin regex fragil).
#
# Exit codes (issue #13): 2=config/deps invalidas, 3=HEALTH_URL con esquema
# invalido, 4=timestamp de systemd ilegible, 5=el servicio no reinicio,
# 6=smoke test fallo (status!=ok o sin respuesta), 7=servicio no-active,
# 8=/salud sin campo commit, 9=commit vivo != commit desplegado,
# 10=sudo -n sin permiso NOPASSWD (ver "Sudoers minimo" en docs/salud-endpoint.md).
#
# Falla claro y se detiene en cuanto una etapa no cumple. Cada etapa imprime
# lo que hace, y la ultima confirma que el proceso vivo esta corriendo el
# commit nuevo comparando el hash reportado por /salud contra el commit
# desplegado ademas del timestamp de inicio del servicio.

set -euo pipefail

if ! command -v jq >/dev/null 2>&1; then
  echo "deploy: falta 'jq' (necesario para leer el JSON del endpoint de salud)." >&2
  exit 2
fi

# Path FIJO (issue #22, coherente con ADR 001): sin override por variable de
# entorno — un env var apuntando a un archivo arbitrario que se source-a es
# ejecucion de codigo sin rastro.
CONFIG="scripts/deploy.env"
if [[ ! -f "$CONFIG" ]]; then
  echo "deploy: falta $CONFIG (configuracion del repo)." >&2
  echo "deploy: crear con SERVICE_NAME, HEALTH_URL, MIGRATIONS_CMD (opcional), BRANCH (opcional)." >&2
  exit 2
fi

# Contrato de permisos (issue #22): rechazar deploy.env ajeno o escribible
# por otros ANTES de ejecutarlo via source.
CONFIG_OWNER="$(stat -c '%U' "$CONFIG")"
CONFIG_PERMS="$(stat -c '%a' "$CONFIG")"
if [[ "$CONFIG_OWNER" != "$(id -un)" && "$CONFIG_OWNER" != "root" ]]; then
  echo "deploy: $CONFIG pertenece a '$CONFIG_OWNER' (esperado: $(id -un) o root). No lo ejecuto." >&2
  exit 2
fi
if [[ "${CONFIG_PERMS: -1}" == [2367] ]]; then
  echo "deploy: $CONFIG es escribible por otros (permisos $CONFIG_PERMS). No lo ejecuto." >&2
  echo "deploy: chmod 640 $CONFIG y reintentar." >&2
  exit 2
fi
# shellcheck disable=SC1090
source "$CONFIG"

: "${SERVICE_NAME:?deploy: falta SERVICE_NAME en $CONFIG}"
: "${HEALTH_URL:?deploy: falta HEALTH_URL en $CONFIG}"
# Issue #13: solo http/https — un file:// o un endpoint de metadata no son
# un healthcheck, son un vector.
case "$HEALTH_URL" in
  http://*|https://*) ;;
  *) echo "deploy: HEALTH_URL debe ser http:// o https:// (recibido: $HEALTH_URL)" >&2; exit 3 ;;
esac
BRANCH="${BRANCH:-main}"
MIGRATIONS_CMD="${MIGRATIONS_CMD:-}"

echo "==> [1/5] git switch $BRANCH && pull --ff-only"
git switch "$BRANCH"
git pull --ff-only

TARGET_COMMIT="$(git rev-parse HEAD)"
echo "==> commit objetivo: $TARGET_COMMIT"

if [[ -n "$MIGRATIONS_CMD" ]]; then
  echo "==> [2/5] migraciones: $MIGRATIONS_CMD"
  # Issue #22: SIN eval. Word-splitting simple y ejecucion directa — sin
  # pipes, redirecciones ni sustituciones. Shell necesario => script versionado.
  read -r -a MIG_ARR <<< "$MIGRATIONS_CMD"
  "${MIG_ARR[@]}"
else
  echo "==> [2/5] migraciones: nada declarado, salto"
fi

echo "==> [3/5] restart de $SERVICE_NAME"
BEFORE_TS="$(systemctl show -p ActiveEnterTimestamp --value "$SERVICE_NAME" 2>/dev/null || true)"
# Issue #13: sudo -n — sin NOPASSWD falla claro en vez de colgarse esperando
# password en corridas no interactivas (timer/CI).
if ! sudo -n systemctl restart "$SERVICE_NAME"; then
  echo "deploy: sudo -n fallo — falta la regla NOPASSWD para systemctl restart $SERVICE_NAME" >&2
  echo "deploy: ver 'Sudoers minimo' en docs/salud-endpoint.md" >&2
  exit 10
fi
# Issue #13: polling del timestamp con deadline en vez de sleep fijo — bajo
# carga systemd puede tardar mas de 2s y el sleep magico daba falso negativo.
RESTART_DEADLINE=$((SECONDS + 30))
AFTER_TS="$BEFORE_TS"
while (( SECONDS < RESTART_DEADLINE )); do
  AFTER_TS="$(systemctl show -p ActiveEnterTimestamp --value "$SERVICE_NAME" 2>/dev/null || true)"
  [[ -n "$AFTER_TS" && "$AFTER_TS" != "$BEFORE_TS" ]] && break
  sleep 1
done
if [[ -z "$AFTER_TS" ]]; then
  echo "deploy: no pude leer ActiveEnterTimestamp de $SERVICE_NAME" >&2
  exit 4
fi
if [[ "$BEFORE_TS" == "$AFTER_TS" ]]; then
  echo "deploy: ActiveEnterTimestamp NO cambio en 30s ($BEFORE_TS)." >&2
  echo "deploy: $SERVICE_NAME no reinicio realmente; algo se comio el restart." >&2
  exit 5
fi
echo "deploy: $SERVICE_NAME reinicio: $BEFORE_TS -> $AFTER_TS"

HEALTH_DEADLINE="${HEALTH_DEADLINE:-60}"
echo "==> [4/5] smoke test contra $HEALTH_URL (deadline ${HEALTH_DEADLINE}s)"
# Polling con deadline (hallazgo M2 de la revision del PR #12): un solo curl
# 2s despues del restart fallaba espurio con servicios que tardan en estar
# listos (migraciones al boot, warm-up), y "reintentar a mano hasta que pase"
# destruye la autoridad del gate.
DEADLINE=$((SECONDS + HEALTH_DEADLINE))
HEALTH_BODY=""
HEALTH_STATUS=""
while (( SECONDS < DEADLINE )); do
  if HEALTH_BODY="$(curl --fail --silent --max-time 10 "$HEALTH_URL" 2>/dev/null)"; then
    HEALTH_STATUS="$(printf '%s' "$HEALTH_BODY" | jq -r '.status // empty')"
    [[ "$HEALTH_STATUS" == "ok" ]] && break
  fi
  sleep 3
done
if [[ "$HEALTH_STATUS" != "ok" ]]; then
  echo "deploy: smoke test FALLO — $HEALTH_URL no respondio status='ok' en ${HEALTH_DEADLINE}s." >&2
  # Issue #13: solo campos whitelisteados al log — un body completo podria
  # arrastrar secrets si el endpoint degradado los filtrara.
  echo "deploy: status='$(printf %s "${HEALTH_BODY:-}" | jq -r ".status // \"<sin respuesta>\"" 2>/dev/null)' commit='$(printf %s "${HEALTH_BODY:-}" | jq -r ".commit // \"?\"" 2>/dev/null)'" >&2
  exit 6
fi
echo "deploy: smoke OK (status=ok)."

echo "==> [5/5] confirmacion final: proceso vivo corre commit desplegado"
STATE="$(systemctl show -p ActiveState --value "$SERVICE_NAME")"
if [[ "$STATE" != "active" ]]; then
  echo "deploy: $SERVICE_NAME esta en estado '$STATE', no 'active'" >&2
  exit 7
fi
LIVE_COMMIT="$(printf '%s' "$HEALTH_BODY" | jq -r '.commit // empty')"
if [[ -z "$LIVE_COMMIT" ]]; then
  echo "deploy: /salud no reporta 'commit'; contrato del endpoint incumplido." >&2
  echo "deploy: sin ese campo, no se puede validar que el proceso vivo corre '$TARGET_COMMIT'." >&2
  exit 8
fi
if [[ "$LIVE_COMMIT" != "$TARGET_COMMIT" ]]; then
  echo "deploy: el proceso vivo reporta commit '$LIVE_COMMIT'," >&2
  echo "deploy: pero se desplego '$TARGET_COMMIT'." >&2
  echo "deploy: systemd reinicio otra cosa (probable WorkingDirectory apuntando a otro checkout)." >&2
  exit 9
fi
echo "deploy: $SERVICE_NAME activo desde $AFTER_TS, corriendo commit $TARGET_COMMIT (confirmado por /salud)."
echo "deploy: OK."
