#!/bin/bash
# Installation NEMAPI Bridge v2.1 (DOM only — pas de xdotool)

set -e
cd "$(dirname "$0")"

echo "[1/3] Environnement Python..."
if [ ! -d venv ]; then
  python3 -m venv venv
fi
# shellcheck disable=SC1091
source venv/bin/activate
pip install -q -r requirements.txt

echo "[2/3] OK — proxy OpenAI + extension Firefox DOM"
echo "[3/3] Suite manuelle :"
echo "  1. source venv/bin/activate && python proxy.py"
echo "  2. Firefox about:debugging → charger extension/"
echo "  3. chat.deepseek.com → Capturer + Connecter"
echo "Terminé."
