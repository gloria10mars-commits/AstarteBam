#!/bin/bash
# Wrapper: lance le serveur NEMESIS dans le venv
cd "$(dirname "$0")"
source venv/bin/activate
exec python server.py "$@"
