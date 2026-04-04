$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

python -m pip install -r requirements.txt
python scripts/build_fabric_server.py

Write-Host ""
Write-Host "Fabric bundle created under output/server-bundle"
Write-Host "Run .\\output\\server-bundle\\start.bat or use Docker compose."
