#!/usr/bin/env bash
# NEMAPI Bridge : premier plan par défaut. Ctrl+C ferme le proxy et enregistre le log.
set -u
cd "$(dirname "$0")"
export NEMAPI_HOST="${NEMAPI_HOST:-0.0.0.0}"
export NEMAPI_PORT="${NEMAPI_PORT:-8080}"
PY="../../.venv/bin/python"; [ -x "$PY" ] || PY="python3"
mkdir -p logs
if ss -tln 2>/dev/null | grep -q ":${NEMAPI_PORT} "; then
  echo "[NEMAPI] Déjà en écoute sur le port ${NEMAPI_PORT}."
  curl -sS "http://127.0.0.1:${NEMAPI_PORT}/health" || true; echo
  echo "[NEMAPI] Pour reprendre la main : ./stop_proxy.sh puis ./start_proxy.sh"
  exit 2
fi
PID=""
cleanup() {
  code=$?
  trap - INT TERM EXIT
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    echo "[NEMAPI] Arrêt du proxy PID $PID (signal reçu)" | tee -a logs/proxy.log
    kill -TERM "$PID" 2>/dev/null || kill -INT "$PID" 2>/dev/null || true
    sleep 1
    kill -KILL "$PID" 2>/dev/null || true
    wait "$PID" 2>/dev/null || true
  fi
  rm -f logs/proxy.pid
  echo "[NEMAPI] Arrêt terminé code=$code" | tee -a logs/proxy.log
  exit "$code"
}
trap cleanup INT TERM EXIT
echo "[NEMAPI] Démarrage premier plan avec $PY sur ${NEMAPI_HOST}:${NEMAPI_PORT}" | tee -a logs/proxy.log
"$PY" proxy.py >> logs/proxy.log 2>&1 &
PID=$!
echo "$PID" > logs/proxy.pid
wait "$PID"
status=$?
PID=""
trap - INT TERM EXIT
rm -f logs/proxy.pid
echo "[NEMAPI] Proxy terminé code=$status" | tee -a logs/proxy.log
exit "$status"
