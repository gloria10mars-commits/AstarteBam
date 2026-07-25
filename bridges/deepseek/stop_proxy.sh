#!/usr/bin/env bash
set -u
cd "$(dirname "$0")"
port="${NEMAPI_PORT:-8080}"
pids=""
if [ -f logs/proxy.pid ]; then pids="$(cat logs/proxy.pid 2>/dev/null || true)"; fi
listener="$(ss -ltnp 2>/dev/null | sed -n "s/.*:${port} .*pid=\\([0-9]*\\).*/\\1/p" | head -1)"
case " $pids " in *" $listener "*) ;; *) pids="$pids $listener";; esac
found=0
for pid in $pids; do
  [ -n "$pid" ] || continue
  if kill -0 "$pid" 2>/dev/null; then
    kill -TERM "$pid" 2>/dev/null || kill -INT "$pid" 2>/dev/null || true
    sleep 1
    kill -KILL "$pid" 2>/dev/null || true
    echo "[NEMAPI] Arrêt demandé au PID $pid"; found=1
  fi
done
rm -f logs/proxy.pid
[ "$found" = 0 ] && echo "[NEMAPI] Aucun proxy trouvé"
