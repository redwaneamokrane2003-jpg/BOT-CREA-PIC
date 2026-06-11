#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if command -v python3.10 >/dev/null 2>&1; then
  python3.10 run.py --setup --download-models
else
  python3 run.py --setup --download-models
fi

