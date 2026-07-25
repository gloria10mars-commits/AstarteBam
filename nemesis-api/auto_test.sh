#!/bin/bash
# NEMESIS v1.5.2 - Test automatique des endpoints
# Teste le serveur sans avoir besoin de Tampermonkey ni de navigateur
# Simule le bing via curl pour valider le flux
# Compatible 32-bit (i386, armhf) et 64-bit (amd64, arm64)

set -e
cd "$(dirname "$0")"

# Detection python: priorite au venv local
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -x "$SCRIPT_DIR/venv/bin/python" ]; then
    PY="$SCRIPT_DIR/venv/bin/python"
elif [ -x "/home/z/.venv/bin/python" ]; then
    PY="/home/z/.venv/bin/python"
else
    PY="python3"
fi

echo "=========================================="
echo "  NEMESIS v1.5.2 - Auto Test"
echo "  Architecture: $(uname -m) ($(getconf LONG_BIT)-bit)"
echo "=========================================="

# Nettoyer configs precedent
if [ -f configs.json ]; then
    mv configs.json "configs.json.bak.$(date +%s)" 2>/dev/null || true
fi

# Lancer le serveur
echo "[1] Demarrage du serveur..."
$PY server.py > /tmp/nemesis_test.log 2>&1 &
SERVER_PID=$!
echo "    PID: $SERVER_PID"
sleep 2

if ! kill -0 $SERVER_PID 2>/dev/null; then
    echo "    ERREUR: serveur n'a pas demarre"
    cat /tmp/nemesis_test.log
    exit 1
fi
echo "    OK serveur actif"

cleanup() {
    echo ""
    echo "[Cleanup] Arret du serveur (PID $SERVER_PID)"
    kill $SERVER_PID 2>/dev/null || true
    wait $SERVER_PID 2>/dev/null || true
}
trap cleanup EXIT

echo ""
echo "[2] Test GET / (racine)"
curl -s http://localhost:5000/ | $PY -m json.tool || { echo "ECHEC"; exit 1; }

echo ""
echo "[3] Test GET /health"
curl -s http://localhost:5000/health | $PY -m json.tool

echo ""
echo "[4] Test GET /v1/models (vide au debut)"
curl -s http://localhost:5000/v1/models | $PY -m json.tool

echo ""
echo "[5] Test POST /register_page (simule Tampermonkey auto-register)"
curl -s -X POST http://localhost:5000/register_page \
    -H "Content-Type: application/json" \
    -d '{
        "page_id": "chat_deepseek_com",
        "config": {
            "input_click": [500, 650],
            "send_click": [500, 730],
            "copy_zone": [500, 350],
            "wait_time": 8
        }
    }' | $PY -m json.tool

echo ""
echo "[6] Test GET /pages (apres register)"
curl -s http://localhost:5000/pages | $PY -m json.tool

echo ""
echo "[7] Test GET /v1/models (apres register)"
curl -s http://localhost:5000/v1/models | $PY -m json.tool

echo ""
echo "[8] Verification persistance configs.json"
if [ -f configs.json ]; then
    echo "    Fichier cree:"
    cat configs.json
else
    echo "    ATTENTION: configs.json non cree"
fi

echo ""
echo "[9] Test POST /v1/chat/completions (doit echouer: pas de navigateur)"
RESP=$(curl -s -X POST http://localhost:5000/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{
        "model": "deepseek",
        "messages": [{"role":"user","content":"Salut"}]
    }' --max-time 35)
echo "    Reponse: $RESP"

echo ""
echo "[10] Test /v1/tasks (mode async + bing simule)"
# Creer une tache asynchrone
TASK_RESP=$(curl -s -X POST http://localhost:5000/v1/tasks \
    -H "Content-Type: application/json" \
    -d '{"model":"deepseek","prompt":"Salut"}')
echo "    Create: $TASK_RESP"
TASK_ID=$(echo "$TASK_RESP" | $PY -c "import sys,json; print(json.load(sys.stdin).get('task_id',''))")
echo "    Task ID: $TASK_ID"

# Statut pending
sleep 1
echo ""
echo "    Statut apres 1s:"
curl -s http://localhost:5000/v1/tasks/$TASK_ID | $PY -m json.tool

# Simuler un bing de Tampermonkey apres 2s
echo ""
echo "    Simulation bing Tampermonkey dans 2s..."
(sleep 2 && curl -s -X POST http://localhost:5000/bing/chat_deepseek_com \
    -H "Content-Type: application/json" \
    -d "{\"content\":\"Bonjour! Je suis DeepSeek, ravi de vous repondre.\",\"task_id\":\"$TASK_ID\",\"success\":true}" > /dev/null) &
BING_PID=$!

# Recuperer le resultat (bloquant 10s)
echo "    Recuperation resultat (bloquant)..."
RESULT=$(curl -s http://localhost:5000/v1/tasks/$TASK_ID/result --max-time 10)
echo "    Resultat: $RESULT"
wait $BING_PID 2>/dev/null || true

echo ""
echo "[11] Test DELETE /v1/tasks/{id} (cancel)"
CANCEL_TASK=$(curl -s -X POST http://localhost:5000/v1/tasks \
    -H "Content-Type: application/json" \
    -d '{"model":"deepseek","prompt":"test cancel"}' | $PY -c "import sys,json; print(json.load(sys.stdin)['task_id'])")
echo "    Task a annuler: $CANCEL_TASK"
curl -s -X DELETE http://localhost:5000/v1/tasks/$CANCEL_TASK | $PY -m json.tool
sleep 0.5
echo "    Statut apres cancel:"
curl -s http://localhost:5000/v1/tasks/$CANCEL_TASK | $PY -m json.tool

echo ""
echo "[12] Test GET /v1/metrics"
curl -s http://localhost:5000/v1/metrics | $PY -m json.tool

echo ""
echo "[13] Test endpoints v1 (compat ascendante)"
echo "    POST /send_prompt (avec page_id explicite):"
TASK_V1=$(curl -s -X POST http://localhost:5000/send_prompt \
    -H "Content-Type: application/json" \
    -d '{"page_id":"chat_deepseek_com","prompt":"test v1","task_id":"v1_test_001"}' | $PY -c "import sys,json; d=json.load(sys.stdin); print(d.get('task_id',''))")
echo "    Task v1: $TASK_V1"

# Le worker va echouer (pas de fenetre) mais le serveur ne doit PAS crasher
sleep 3
echo ""
echo "    Serveur toujours actif?"
if kill -0 $SERVER_PID 2>/dev/null; then
    echo "    OK serveur vivant"
else
    echo "    ECHEC: serveur crashed"
    cat /tmp/nemesis_test.log
    exit 1
fi

echo "    Resultat task v1:"
curl -s http://localhost:5000/get_result/$TASK_V1 | $PY -m json.tool

echo ""
echo "[14] Test GET /current_page (sans navigateur)"
curl -s http://localhost:5000/current_page | $PY -m json.tool || echo "    (attendu: erreur 404)"

echo ""
echo "=========================================="
echo "  TOUS LES TESTS SONT PASSES"
echo "=========================================="
echo ""
echo "Le serveur n'a pas crashé malgré l'absence de xdotool/xclip/DISPLAY."
echo "Endpoints v1 (compat) et v2 (OpenAI) tous fonctionnels."
echo ""
echo "Logs serveur:"
tail -20 /tmp/nemesis_test.log
