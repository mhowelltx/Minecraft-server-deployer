#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

python3 -m pip install -r requirements.txt
python3 scripts/build_server.py

echo
echo "Bundle created under output/server-bundle"
echo "Either:"
echo "  1) place a compatible server.jar into output/server-bundle and run ./start.sh"
echo "  2) cd output/server-bundle && docker compose up -d"
