$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

python -m pip install -r requirements.txt
python scripts/build_server.py

Write-Host ""
Write-Host "Bundle created under output/server-bundle"
Write-Host "Either:"
Write-Host "  1) place a compatible server.jar into output/server-bundle and run start.bat"
Write-Host "  2) cd output/server-bundle ; docker compose up -d"
