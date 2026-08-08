# scripts/lib-eventos.sh — emisor comun de eventos JSONL (ADR 002 §2, rev 3).
#
# Se SOURCEA, no se ejecuta. Es la UNICA fuente de verdad del formato de
# linea de eventos.jsonl: lanzar-rol.sh y vigilante-revisiones.sh lo
# referencian en vez de duplicarlo (regla "Contratos: una sola fuente de
# verdad" de CLAUDE.md — issues #46 y #59).
#
# El caller puede definir EVENTOS_DIR antes de sourcear; default: el
# directorio de estado del vigilante.

EVENTOS_DIR="${EVENTOS_DIR:-${HOME}/.fabrica-vigilante}"
EVENTOS_FILE="${EVENTOS_DIR}/eventos.jsonl"
EVENTOS_LOCK="${EVENTOS_DIR}/eventos.lock"
mkdir -p "$EVENTOS_DIR" 2>/dev/null || true

# Escapado JSON minimo para TODO string interpolado en la linea (review
# PR#45 H1/H-B2): backslash, comilla, newline legible, y fuera todo control
# char restante (RFC 8259).
json_str() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  s="${s//$'\n'/ | }"
  s="${s//[[:cntrl:]]/}"
  printf '%s' "$s"
}

# emitir_evento <run_id|-> <repo> <trabajo> <rol> <evento> <resultado_json> <duracion_json> <detalle>
#
#   run_id "-"        => null (eventos del orquestador — ADR 002 rev 3).
#   resultado_json    => crudo a la linea: '"ok"', '"fallo"' o null.
#   duracion_json     => crudo a la linea: numero (ej. 12.345) o null.
#   detalle           => texto libre; se trunca a 1 KiB ANTES de escapar
#                        (review PR#45 r2 H-M2) y se escapa.
#
# NUNCA bloquea al caller: si el archivo no se puede escribir, stderr y
# seguir (ADR 002 §2 — la observabilidad no frena la produccion).
# Concurrencia (H4/H-A1): flock sobre EVENTOS_LOCK (archivo separado; todo
# emisor lockea ESTE mismo archivo) y linea max 4 KiB. En Linux sin flock la
# emision se OMITE con aviso (nunca JSONL intercalado corrupto); el append
# directo queda solo para la maquina del operador (macOS, sin paralelismo).
emitir_evento() {
  local run_id="$1" repo="$2" trabajo="$3" rol="$4" evento="$5"
  local resultado="$6" duracion="$7" detalle="$8"
  local run_json
  if [[ "$run_id" == "-" ]]; then
    run_json="null"
  else
    run_json="\"$(json_str "$run_id")\""
  fi
  detalle="${detalle:0:1024}"
  detalle="$(json_str "$detalle")"
  local linea
  linea="$(printf '{"ts":"%s","run_id":%s,"repo":"%s","trabajo":"%s","rol":"%s","evento":"%s","resultado":%s,"duracion_s":%s,"costo_usd":null,"detalle":"%s"}' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$run_json" "$(json_str "$repo")" \
    "$(json_str "$trabajo")" "$(json_str "$rol")" "$(json_str "$evento")" \
    "$resultado" "$duracion" "$detalle")"
  linea="${linea:0:4096}"
  if command -v flock >/dev/null 2>&1; then
    ( flock 9; printf '%s\n' "$linea" >> "$EVENTOS_FILE" ) 9>>"$EVENTOS_LOCK" 2>/dev/null \
      || echo "lib-eventos: no pude emitir evento a $EVENTOS_FILE (no bloquea)" >&2
  elif [[ "$(uname)" == "Linux" ]]; then
    echo "lib-eventos: flock no disponible en Linux — evento OMITIDO (instalar util-linux)." >&2
  else
    printf '%s\n' "$linea" >> "$EVENTOS_FILE" 2>/dev/null \
      || echo "lib-eventos: no pude emitir evento a $EVENTOS_FILE (no bloquea)" >&2
  fi
}
