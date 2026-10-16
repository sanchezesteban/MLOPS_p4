#!/usr/bin/env bash
# P4-10/P4-12/P4-13/P4-22: procedimiento de "sin red sigue funcionando" para
# la demo y el ensayo. Corre EN LA PI (necesita sudo, nmcli y systemd-run
# locales). Arranca main.py en modo intervalo dentro de tmux (sobrevive al
# corte de red) y apaga el wifi un rato con regreso automático -- el apagado
# corre como unidad systemd independiente de esta sesión SSH, porque la
# propia sesión SSH se cae en cuanto el wifi se apaga.
#
# Uso (en la Pi, dentro de ~/edge):
#   bash sin_red_demo.sh [segundos_sin_red]   # default 65
#
# Después de correrlo, la sesión SSH se cae en unos segundos -- es normal.
# Reconéctate pasados los segundos_sin_red + unos segundos de margen y revisa
# con: tmux attach -t edge   (o `tmux capture-pane -t edge -p` sin adjuntarse)
set -euo pipefail

SECONDS_OFF="${1:-65}"
SESSION="edge"

tmux kill-session -t "$SESSION" 2>/dev/null || true
# A propósito: tmux le pasa este string literal a su propio shell anidado,
# que es quien expande $HOME, no este script.
# shellcheck disable=SC2016
tmux new-session -d -s "$SESSION" '$HOME/edge-venv/bin/python main.py --config config.json'
echo "Sesión tmux '$SESSION' arrancada (modo intervalo). Capturas en curso..."
sleep 2

echo "Apagando wifi por ${SECONDS_OFF}s, con regreso automático (unidad systemd independiente de este SSH)..."
sudo systemd-run --unit=wifi-demo-sin-red bash -c \
  "nmcli radio wifi off; sleep ${SECONDS_OFF}; nmcli radio wifi on"

echo "Listo. La red (y este SSH) se va a caer en unos segundos -- es lo esperado."
echo "Reconéctate en ~$((SECONDS_OFF + 15))s y revisa con:"
echo "  tmux capture-pane -t edge -p"
echo "  ls -la --time-style=full-iso capturas/*.json | tail -30"
echo "  cat capturas/log.jsonl"
