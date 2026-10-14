#!/usr/bin/env bash
# P4-16 / rúbrica 4.3: provoca un fallo de envío controlado y reversible en la
# ingesta de capturas. `off` reserva 0 ejecuciones concurrentes para la Lambda:
# API Gateway responde 5xx sin llegar a S3 ni a DynamoDB. `on` quita la reserva y
# la ingesta vuelve a aceptar eventos. Ningún dato se borra ni se modifica.
#
# Uso (desde la raíz del repo, con un perfil administrador de la cuenta P4):
#   AWS_PROFILE=<admin> bash scripts/p4_ingesta_fallo.sh off      # provoca el fallo
#   AWS_PROFILE=<admin> bash scripts/p4_ingesta_fallo.sh on       # restaura
#   AWS_PROFILE=<admin> bash scripts/p4_ingesta_fallo.sh status
#
# Demo: off -> la Pi envía y marca `error` -> on -> la Pi reintenta el mismo
# capture_id -> 201 y un solo registro.
set -euo pipefail

FUNCTION="${INGEST_FUNCTION:-mlops-p4-ingest}"
REGION="${AWS_REGION:-us-east-2}"

status() {
  local reserved
  reserved="$(aws lambda get-function-concurrency --function-name "$FUNCTION" \
    --region "$REGION" --query ReservedConcurrentExecutions --output text)"
  if [ "$reserved" = "0" ]; then
    echo "ingesta: DESHABILITADA (fallo controlado activo)"
  else
    echo "ingesta: habilitada"
  fi
}

case "${1:-}" in
  off)
    aws lambda put-function-concurrency --function-name "$FUNCTION" --region "$REGION" \
      --reserved-concurrent-executions 0 >/dev/null
    status
    ;;
  on)
    aws lambda delete-function-concurrency --function-name "$FUNCTION" --region "$REGION"
    status
    ;;
  status)
    status
    ;;
  *)
    echo "uso: $0 off|on|status" >&2
    exit 2
    ;;
esac
