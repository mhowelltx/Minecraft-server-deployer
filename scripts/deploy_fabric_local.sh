#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

python3 -m pip install -r requirements.txt
python3 scripts/build_fabric_server.py

echo
echo "Fabric bundle created under output/server-bundle"
echo "Run ./output/server-bundle/start.sh or use Docker compose."
