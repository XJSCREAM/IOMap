#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  echo 'Create .venv and install requirements.lock.txt first; see README.md.'
  exit 1
fi
exec .venv/bin/python app.py
