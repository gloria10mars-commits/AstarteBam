#!/usr/bin/env bash
# Installation locale d'Astarte BAM — ne demande ni ne stocke de clé dans ce script.
set -Eeuo pipefail
BASE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$BASE_DIR"

info(){ printf '\n\033[1;36m[ASTARTE]\033[0m %s\n' "$*"; }
warn(){ printf '\n\033[1;33m[ATTENTION]\033[0m %s\n' "$*" >&2; }
fail(){ printf '\n\033[1;31m[ERREUR]\033[0m %s\n' "$*" >&2; exit 1; }

command -v python3 >/dev/null 2>&1 || fail "Python 3 est requis."
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,8) else 1)' || fail "Python 3.8 ou supérieur est requis."

info "Création de l'environnement Python local .venv"
python3 -m venv .venv
PYTHON="$BASE_DIR/.venv/bin/python"
"$PYTHON" -m pip install --upgrade pip setuptools wheel

info "Installation des dépendances du CLI"
"$PYTHON" -m pip install --upgrade rich

info "Installation de Gemini-Chat-API (local prioritaire)"
LOCAL_GEMINI="/home/leon/Gemini-Chat-API"
if [ -d "$LOCAL_GEMINI/gemini_client" ]; then
  if ! "$PYTHON" -m pip install -e "$LOCAL_GEMINI"; then
    warn "Installation locale Gemini échouée."
  else
    info "Gemini-Chat-API local installé depuis $LOCAL_GEMINI"
  fi
elif command -v git >/dev/null 2>&1; then
  if ! "$PYTHON" -m pip install --upgrade 'git+https://github.com/OEvortex/Gemini-Chat-API.git'; then
    warn "Gemini-Chat-API n'a pas pu être installé."
  fi
else
  warn "Ni Gemini local ni git : intégration Gemini ignorée."
fi

info "Rappel DeepSeek / NEMAPI"
if [ -x /home/leon/Deepseek_API_bridge/start_proxy.sh ]; then
  echo "  Bridge: /home/leon/Deepseek_API_bridge/start_proxy.sh"
  echo "  Puis Firefox extension/ + chat.deepseek.com (Capturer + Connecter)"
  echo "  Activez NEMAPI_ENABLED=true dans .env ou /model nemapi 1"
fi

if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
  info "Fichier .env créé avec des valeurs locales sûres."
else
  chmod 600 .env 2>/dev/null || true
  info "Fichier .env existant conservé."
fi
mkdir -p .secrets workspace/logs
chmod 700 .secrets
chmod +x astarte install_astartebam.sh

info "Vérification du code"
"$PYTHON" -m py_compile server.py cli.py core/*.py

cat <<'GUIDE'

============================================================
INSTALLATION TERMINÉE
============================================================

1. Lancez le projet :
   ./astarte

2. Au démarrage, choisissez :
   1 = individuel
   2 = collaboratif

3. Dans le CLI, ajoutez au maximum deux clés par fournisseur :
   /cle groq
   /cle fireworks
   /cle cohere
   /cle nvidia

4. Pour Gemini, n'envoyez jamais vos cookies dans un chat.
   Saisissez-les localement :
   /gemini-cookie 1
   /gemini-cookie 2

5. Consultez le tableau de bord :
   /dashboard

6. Les commandes sensibles demandent toujours votre accord.
   Les mots de passe de sudo sont demandés directement dans le CLI.

Les clés et les sessions sont locales : .env et .secrets/.
Ne les ajoutez jamais à Git ou à un ZIP partagé.
============================================================
GUIDE
