#!/usr/bin/env bash
# scripts/sincronizar-desde-fabrica.sh — actualiza los artefactos vendored de fabrica.
#
# Uso:
#   scripts/sincronizar-desde-fabrica.sh <sha-commit-40-hex>
#
# Ejemplo:
#   scripts/sincronizar-desde-fabrica.sh 539c6a0219bbd375116bee035d729a48327f911a
#
# Este script vive en fabrica como referencia canonica. Cada repo producto lo
# copia (vendored) y lo mantiene alineado con el commit que consume.
#
# Que hace (y solo esto):
#   1. Descarga el tarball del commit SHA desde el repo fabrica en GitHub.
#   2. Copia UNO A UNO los archivos declarados en la ALLOWLIST de abajo.
#   3. Actualiza FABRICA_VERSION con el SHA nuevo.
#   4. Deja el checkout con cambios sin commitear, listos para armar el PR.
#
# Que NUNCA hace:
#   - Borrado recursivo sobre el working tree del repo producto (el unico
#     rm -rf es la limpieza del directorio temporal de mktemp al salir).
#   - Copiar directorios completos (siempre archivo por archivo).
#   - Tocar docs/adr/ (los ADRs son del repo producto).
#   - Tocar .claude/contexto-producto.md (el contexto de usuario es del repo producto).
#   - Tocar archivos fuera de la ALLOWLIST.
#   - Aceptar override del repo de origen por variable de entorno.
#
# El path del repo canonico esta hardcodeado abajo. Cambiarlo requiere editar
# este script y revisar el diff en un PR (qa + seguridad + arquitecto).
#
# El commit y el PR los hace el operador humano, con revision qa + seguridad
# (y arquitecto si el diff toca contratos). Ver docs/adr/001-sync-fabrica-a-repos-producto.md.

set -euo pipefail

# Repo canonico de fabrica. HARDCODEADO a proposito: no se acepta override.
readonly REPO_FABRICA="giovandojorgegustavo-hub/fabrica"

# Allowlist explicita de archivos que fabrica propaga a los repos producto.
# Cada linea es un path relativo a la raiz del repo. Solo archivos regulares:
# nunca directorios, nunca globs, nunca symlinks.
#
# Los repos producto son dueños de todo lo que NO este listado aca, en
# particular:
#   - docs/adr/            (ADRs propios del producto)
#   - .claude/contexto-producto.md
#   - src/, tests/, migrations/
#   - scripts/deploy.env, .fabrica-version legacy, etc.
readonly ALLOWLIST=(
  "CLAUDE.md"
  ".claude/agents/backend.md"
  ".claude/agents/frontend.md"
  ".claude/agents/ux.md"
  ".claude/agents/qa.md"
  ".claude/agents/seguridad.md"
  ".claude/agents/arquitecto.md"
  ".claude/agents/producto.md"
  "scripts/deploy.sh"
  "scripts/lanzar-rol.sh"
  "scripts/lib-eventos.sh"
  "scripts/sincronizar-desde-fabrica.sh"
  "docs/identidades.md"
  "docs/salud-endpoint.md"
)

if [[ $# -ne 1 ]]; then
  echo "uso: $0 <sha-commit-40-hex>" >&2
  echo "ej:  $0 539c6a0219bbd375116bee035d729a48327f911a" >&2
  exit 2
fi

SHA="$1"

# Valida forma de SHA (40 hex minusculas) antes de tocar red o disco.
if [[ ! "$SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "sincronizar: sha invalido '$SHA'. Formato esperado: 40 hex minusculas." >&2
  exit 3
fi

if [[ ! -d ".git" ]]; then
  echo "sincronizar: no estoy en la raiz de un repo git." >&2
  exit 4
fi

TMPDIR="$(mktemp -d)"
# Temporales .sync-* creados en el working tree (issue #19): se registran
# aca para que el trap los limpie si el script muere entre mktemp y mv.
SYNC_TMPS=()
trap 'rm -rf "$TMPDIR"; rm -f ${SYNC_TMPS[@]+"${SYNC_TMPS[@]}"}' EXIT

echo "==> descargando commit $SHA de $REPO_FABRICA"
if command -v gh >/dev/null 2>&1; then
  # Issue #20: los archive URLs publicos devuelven 404 en repos privados.
  # gh api usa la autenticacion del operador y funciona en ambos casos;
  # ademas la API resuelve el SHA contra el repo canonico declarado arriba.
  if ! gh api "repos/${REPO_FABRICA}/tarball/${SHA}" > "$TMPDIR/fabrica.tar.gz"; then
    echo "sincronizar: gh api fallo descargando el tarball de $SHA" >&2
    exit 5
  fi
else
  # Fallback sin gh: solo funciona con repos publicos.
  URL="https://github.com/${REPO_FABRICA}/archive/${SHA}.tar.gz"
  echo "==> (sin gh) descargando $URL"
  if ! curl --fail --silent --show-error --location \
         --proto '=https' --proto-redir '=https' \
         --max-time 60 \
         "$URL" -o "$TMPDIR/fabrica.tar.gz"; then
    echo "sincronizar: no pude descargar $URL (repo privado? instalar gh)" >&2
    exit 5
  fi
fi

echo "==> extrayendo"
# Issue #16: pre-validar el tarball — rechazar rutas absolutas o traversal
# antes de extraer (GNU tar rechaza ../ por default, pero explicito > implicito).
if tar -tzf "$TMPDIR/fabrica.tar.gz" | grep -Eq '(^/|\.\./)'; then
  echo "sincronizar: el tarball contiene rutas absolutas o traversal; rechazo." >&2
  exit 6
fi
tar --no-same-owner --no-same-permissions -xzf "$TMPDIR/fabrica.tar.gz" -C "$TMPDIR"
SRC="$(find "$TMPDIR" -maxdepth 1 -type d -name '*fabrica-*' | head -n1)"
if [[ -z "$SRC" || ! -d "$SRC" ]]; then
  echo "sincronizar: no encontre el directorio extraido en $TMPDIR" >&2
  exit 6
fi

copiar_archivo() {
  local rel="$1"
  local src="$SRC/$rel"
  local dst="./$rel"

  # No seguir symlinks del tarball.
  if [[ -L "$src" ]]; then
    echo "sincronizar: $rel es symlink en el tarball; rechazo por seguridad." >&2
    return 1
  fi
  # Archivo de la allowlist ausente en el commit = fallo duro. Si fabrica
  # retira un archivo, lo retira de la allowlist en el mismo commit; un skip
  # silencioso dejaria el vendored viejo con FABRICA_VERSION nuevo (drift).
  if [[ ! -f "$src" ]]; then
    echo "sincronizar: $rel no existe como archivo regular en el commit $SHA." >&2
    echo "sincronizar: allowlist y commit desalineados; no continuo." >&2
    return 1
  fi

  # Rechazo mkdir sobre paths con '..' (defensa aunque el allowlist ya lo evita).
  case "$rel" in
    *..*|/*)
      echo "sincronizar: path invalido '$rel'; rechazo." >&2
      return 1
      ;;
  esac

  # Issue #19: dentro de una funcion invocada bajo `|| ...`, bash SUSPENDE
  # set -e — cada comando necesita chequeo explicito, o un cp fallido a
  # mitad (disco lleno) instalaria un archivo truncado con exit 0.
  if ! mkdir -p "$(dirname "$dst")"; then
    echo "sincronizar: mkdir fallo para $rel" >&2
    return 1
  fi
  # Copia via temporal + mv (rename atomico). NUNCA cp -f directo al destino:
  # este script esta en su propia allowlist, y cp -f truncaria el mismo inode
  # que bash esta leyendo mientras corre (ejecucion corrupta no determinista).
  # mv reemplaza la entrada de directorio y preserva el inode viejo abierto.
  local tmp
  if ! tmp="$(mktemp "$(dirname "$dst")/.sync-XXXXXX")"; then
    echo "sincronizar: mktemp fallo para $rel" >&2
    return 1
  fi
  SYNC_TMPS+=("$tmp")
  if ! cp -f "$src" "$tmp"; then
    rm -f "$tmp"
    echo "sincronizar: cp fallo para $rel (disco lleno?); temporal descartado, destino intacto" >&2
    return 1
  fi
  # Issue #27: mktemp crea el temporal con modo 0600 y mv hereda ESE modo, no
  # el del archivo fuente — los scripts llegaban sin bit de ejecucion y el
  # vigilante (correctamente) se negaba a usar un lanzador no ejecutable.
  if ! chmod --reference="$src" "$tmp"; then
    rm -f "$tmp"
    echo "sincronizar: chmod fallo para $rel; temporal descartado, destino intacto" >&2
    return 1
  fi
  if ! mv -f "$tmp" "$dst"; then
    rm -f "$tmp"
    echo "sincronizar: mv fallo para $rel; destino intacto" >&2
    return 1
  fi
  echo "  copiado: $rel"
  # Issue #16: si el repo producto ignora este path, el commit no lo captura
  # y queda drift silencioso — avisar, no fallar (decision del operador).
  if git check-ignore -q "$rel" 2>/dev/null; then
    echo "  AVISO: $rel esta en .gitignore del repo — el sync lo copio pero el commit NO lo va a incluir." >&2
  fi
}

echo "==> vendoring (allowlist de ${#ALLOWLIST[@]} archivos, sin borrado)"
FALLOS=0
for rel in "${ALLOWLIST[@]}"; do
  copiar_archivo "$rel" || FALLOS=$((FALLOS + 1))
done
if [[ $FALLOS -gt 0 ]]; then
  echo "sincronizar: $FALLOS archivos fallaron. Revisa arriba." >&2
  exit 7
fi

printf '%s\n' "$SHA" > FABRICA_VERSION
echo "==> FABRICA_VERSION -> $SHA"

echo
echo "sincronizar: listo. Cambios sin commitear."
echo "sincronizar: revisa 'git status' y 'git diff', arma la rama y abri PR."
echo "sincronizar: el PR pasa por qa + seguridad como cualquier cambio de proceso."
