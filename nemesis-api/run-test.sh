#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
exec bash auto_test.sh "$@"
