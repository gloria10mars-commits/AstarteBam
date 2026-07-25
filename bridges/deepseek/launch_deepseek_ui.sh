#!/usr/bin/env bash
# Ouvre Firefox sur DeepSeek (DISPLAY :0) pour l'extension NEMAPI
set -euo pipefail
export DISPLAY="${DISPLAY:-:0}"
EXT_DIR="$(cd "$(dirname "$0")/extension" && pwd)"

if ! xdpyinfo >/dev/null 2>&1; then
  echo "DISPLAY $DISPLAY inaccessible"
  exit 1
fi

# Préférer un profil existant
PROFILE="${FIREFOX_PROFILE:-nm4ad5n5.default-esr}"
# --new-instance évite de bloquer si déjà ouvert
firefox -P "$PROFILE" --new-tab "https://chat.deepseek.com" \
  about:debugging#/runtime/this-firefox >/dev/null 2>&1 &
echo "Firefox lancé. Chargez l'extension depuis: $EXT_DIR"
echo "Puis: Capturer l'onglet DeepSeek + Connecter au proxy."
