#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if [ -x ".venv/bin/python" ]; then
  .venv/bin/python run.py
elif command -v python3.10 >/dev/null 2>&1; then
  python3.10 run.py
else
  python3 run.py
fi

