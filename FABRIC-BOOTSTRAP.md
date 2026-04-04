# Fabric Bootstrap Path

This is the first fully automated runnable path for the repo.

## What it does

`scripts/build_fabric_server.py` will:
- read `server-config.yaml`
- bootstrap a Fabric server into `output/server-bundle`
- download Modrinth mods or copy local mods
- generate `eula.txt`
- generate `server.properties`
- generate start scripts
- generate Docker files
- generate `manifest.json`

## Requirements

- Python 3.11+
- Java available in PATH

## Local use

### Windows

```powershell
python -m pip install -r requirements.txt
python scripts/build_fabric_server.py
```

### Linux/macOS

```bash
python3 -m pip install -r requirements.txt
python3 scripts/build_fabric_server.py
```

## GitHub Actions

Run the workflow:

**Build Fabric Server Pack**

That workflow sets up both Python and Java.

## Output

The runnable bundle is generated here:

```text
output/server-bundle
```

For Fabric builds, `start.sh` or `start.bat` should be runnable without manually dropping in a server jar.
