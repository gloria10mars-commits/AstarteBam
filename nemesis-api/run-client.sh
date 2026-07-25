#!/bin/bash
# Wrapper: lance le client NEMESIS dans le venv
cd "$(dirname "$0")"
source venv/bin/activate
exec python client.py "$@"
