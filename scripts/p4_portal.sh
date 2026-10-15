#!/usr/bin/env bash
# P4-18: operación del portal desplegado en EC2 (sin SSH; todo por SSM).
#
# Uso (desde la raíz del repo, con un perfil administrador de la cuenta P4):
#   AWS_PROFILE=<admin> bash scripts/p4_portal.sh deploy [rama]   # git pull + docker compose up --build
#   AWS_PROFILE=<admin> bash scripts/p4_portal.sh status          # estado de la EC2 y de los contenedores
#   AWS_PROFILE=<admin> bash scripts/p4_portal.sh logs            # log de arranque (cloud-init)
#   AWS_PROFILE=<admin> bash scripts/p4_portal.sh stop            # apaga la EC2 (deja de cobrar cómputo)
#   AWS_PROFILE=<admin> bash scripts/p4_portal.sh start           # la prende; la URL no cambia (IP elástica)
#
# Al prender, los contenedores vuelven solos (restart: unless-stopped); tarda ~1 min.
set -euo pipefail

REGION="${AWS_REGION:-us-east-2}"
NAME="${PORTAL_NAME:-mlops-p4-portal}"
export MSYS_NO_PATHCONV=1   # Git Bash en Windows no debe reescribir rutas como /opt/portal
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8   # la AWS CLI en Windows imprime el log de cloud-init (UTF-8)

instance_id() {
  aws ec2 describe-instances --region "$REGION" \
    --filters "Name=tag:Name,Values=$NAME" "Name=instance-state-name,Values=pending,running,stopping,stopped" \
    --query 'Reservations[0].Instances[0].InstanceId' --output text
}

run() {
  local id="$1"
  shift
  local command_id
  command_id="$(aws ssm send-command --region "$REGION" --instance-ids "$id" \
    --document-name AWS-RunShellScript --comment "p4_portal.sh" \
    --parameters "commands=[\"$*\"]" --timeout-seconds 1800 \
    --query Command.CommandId --output text)"
  aws ssm wait command-executed --region "$REGION" --command-id "$command_id" --instance-id "$id" || true
  aws ssm get-command-invocation --region "$REGION" --command-id "$command_id" --instance-id "$id" \
    --query '[Status, StandardOutputContent, StandardErrorContent]' --output text
}

ID="$(instance_id)"
if [ -z "$ID" ] || [ "$ID" = "None" ]; then
  echo "no encontré la EC2 $NAME en $REGION" >&2
  exit 1
fi

case "${1:-}" in
  deploy)
    run "$ID" "sudo /usr/local/bin/portal-deploy ${2:-main} 2>&1 | tail -40"
    ;;
  status)
    aws ec2 describe-instances --region "$REGION" --instance-ids "$ID" \
      --query 'Reservations[0].Instances[0].[InstanceId,State.Name,PublicIpAddress]' --output text
    run "$ID" "cd /opt/portal && sudo docker compose -f docker-compose.yml -f docker-compose.aws.yml ps --format 'table {{.Service}}\t{{.State}}\t{{.Status}}' && git log -1 --oneline"
    ;;
  logs)
    run "$ID" "sudo tail -60 /var/log/portal-bootstrap.log"
    ;;
  stop)
    aws ec2 stop-instances --region "$REGION" --instance-ids "$ID" --query 'StoppingInstances[0].CurrentState.Name' --output text
    ;;
  start)
    aws ec2 start-instances --region "$REGION" --instance-ids "$ID" --query 'StartingInstances[0].CurrentState.Name' --output text
    aws ec2 wait instance-running --region "$REGION" --instance-ids "$ID"
    echo "EC2 encendida; el portal responde en ~1 min."
    ;;
  *)
    echo "uso: $0 deploy [rama] | status | logs | stop | start" >&2
    exit 2
    ;;
esac
