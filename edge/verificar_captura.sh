#!/usr/bin/env bash
# P4-13/P4-25: confirma que una captura llegó al portal -- consulta la misma
# API de lectura que usa el frontend (GET /captures, sin firma, pública) y
# busca el capture_id. No depende de credenciales de AWS.
#
# Uso: bash verificar_captura.sh <capture_id> [intentos] [espera_s]
set -euo pipefail

CAPTURE_ID="${1:?uso: verificar_captura.sh <capture_id> [intentos] [espera_s]}"
INTENTOS="${2:-6}"
ESPERA_S="${3:-5}"
API_URL="https://el1c2mr69k.execute-api.us-east-2.amazonaws.com"

for intento in $(seq 1 "$INTENTOS"); do
  if curl -s "${API_URL}/captures?limit=50" | python3 -c "
import json, sys
data = json.load(sys.stdin)
found = any(item['capture_id'] == '${CAPTURE_ID}' for item in data['items'])
sys.exit(0 if found else 1)
"; then
    echo "OK: ${CAPTURE_ID} ya aparece en la API de lectura (intento ${intento}/${INTENTOS})"
    exit 0
  fi
  echo "intento ${intento}/${INTENTOS}: todavía no aparece, esperando ${ESPERA_S}s..."
  sleep "$ESPERA_S"
done

echo "NO apareció ${CAPTURE_ID} tras ${INTENTOS} intentos" >&2
exit 1
