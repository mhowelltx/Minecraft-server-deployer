#!/usr/bin/env python3
"""Build a deployable Minecraft server bundle from YAML config.

First version capabilities:
- Reads server-config.yaml and mods.yaml
- Generates server.properties and eula.txt
- Creates start scripts for Windows/Linux
- Copies local mods when mode=local_only
- Resolves Modrinth versions/files when mode=modrinth
- Produces an output bundle under output/server-bundle

This first cut intentionally does not try to auto-download Forge/Fabric server loaders yet.
It scaffolds the environment so the next iteration can add loader bootstrap reliably.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "server-config.yaml"
MODS_PATH = ROOT / "mods.yaml"
OUTPUT_ROOT = ROOT / "output" / "server-bundle"
MODRINTH_PROJECT_API = "https://api.modrinth.com/v2/project/{project_id}/version"
USER_AGENT = "minecraft-server-deployer/0.1"


def load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def ensure_clean_output(output_dir: Path) -> None:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    (output_dir / "mods").mkdir(parents=True, exist_ok=True)
    (output_dir / "config").mkdir(parents=True, exist_ok=True)
    (output_dir / "logs").mkdir(parents=True, exist_ok=True)
    (output_dir / "world").mkdir(parents=True, exist_ok=True)


def truthy(value: Any) -> str:
    return "true" if bool(value) else "false"


def build_server_properties(server_cfg: Dict[str, Any]) -> str:
    lines = [
        f"motd={server_cfg.get('motd', 'Minecraft Server')}",
        f"difficulty={server_cfg.get('difficulty', 'normal')}",
        f"gamemode={server_cfg.get('gamemode', 'survival')}",
        f"pvp={truthy(server_cfg.get('pvp', True))}",
        f"online-mode={truthy(server_cfg.get('online_mode', True))}",
        f"allow-flight={truthy(server_cfg.get('allow_flight', False))}",
        f"max-players={server_cfg.get('max_players', 10)}",
        f"view-distance={server_cfg.get('view_distance', 10)}",
        f"simulation-distance={server_cfg.get('simulation_distance', 10)}",
        f"enable-command-block={truthy(server_cfg.get('enable_command_block', False))}",
        f"white-list={truthy(server_cfg.get('white_list', False))}",
        f"spawn-protection={server_cfg.get('spawn_protection', 0)}",
        f"server-port={server_cfg.get('server_port', 25565)}",
        f"level-seed={server_cfg.get('level_seed', '')}",
    ]
    return "\n".join(lines) + "\n"


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def make_executable(path: Path) -> None:
    current = path.stat().st_mode
    path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def build_start_scripts(output_dir: Path, server_cfg: Dict[str, Any]) -> None:
    min_mem = server_cfg.get("java_memory", {}).get("min", "2G")
    max_mem = server_cfg.get("java_memory", {}).get("max", "4G")

    linux_script = f"""#!/usr/bin/env bash
set -euo pipefail
cd \"$(dirname \"$0\")\"
java -Xms{min_mem} -Xmx{max_mem} -jar server.jar nogui
"""
    windows_script = f"""@echo off
cd /d %~dp0
java -Xms{min_mem} -Xmx{max_mem} -jar server.jar nogui
pause
"""
    write_text(output_dir / "start.sh", linux_script)
    write_text(output_dir / "start.bat", windows_script)
    make_executable(output_dir / "start.sh")


def copy_local_mods(output_dir: Path, local_mods_dir: Path) -> List[Dict[str, str]]:
    installed: List[Dict[str, str]] = []
    if not local_mods_dir.exists():
        return installed
    for item in sorted(local_mods_dir.iterdir()):
        if item.is_file() and item.suffix.lower() == ".jar":
            dest = output_dir / "mods" / item.name
            shutil.copy2(item, dest)
            installed.append({"name": item.name, "source": "local"})
    return installed


def fetch_modrinth_versions(project_id: str, minecraft_version: str, loader: str) -> List[Dict[str, Any]]:
    response = requests.get(
        MODRINTH_PROJECT_API.format(project_id=project_id),
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    versions = response.json()
    filtered = []
    for version in versions:
        game_versions = version.get("game_versions", [])
        loaders = version.get("loaders", [])
        if minecraft_version in game_versions and (loader in loaders or loader == "vanilla"):
            filtered.append(version)
    return filtered


def resolve_modrinth_mod(mod: Dict[str, Any], minecraft_version: str, loader: str) -> Optional[Dict[str, str]]:
    project_id = mod.get("project_id")
    if not project_id:
        return None

    version_id = mod.get("version_id")
    if version_id:
        version_url = f"https://api.modrinth.com/v2/version/{version_id}"
        response = requests.get(version_url, headers={"User-Agent": USER_AGENT}, timeout=30)
        response.raise_for_status()
        version = response.json()
    else:
        versions = fetch_modrinth_versions(project_id, minecraft_version, loader)
        if not versions:
            return None
        version = versions[0]

    files = version.get("files", [])
    if not files:
        return None

    chosen_file = None
    requested_filename = mod.get("filename")
    if requested_filename:
        for file_info in files:
            if file_info.get("filename") == requested_filename:
                chosen_file = file_info
                break
    if chosen_file is None:
        chosen_file = files[0]

    return {
        "name": mod.get("name", project_id),
        "filename": chosen_file["filename"],
        "url": chosen_file["url"],
        "version_id": version.get("id", ""),
        "project_id": project_id,
    }


def download_file(url: str, destination: Path) -> None:
    with requests.get(url, stream=True, headers={"User-Agent": USER_AGENT}, timeout=60) as response:
        response.raise_for_status()
        with destination.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    handle.write(chunk)


def install_mods(output_dir: Path, server_cfg: Dict[str, Any], mods_cfg: Dict[str, Any], source_cfg: Dict[str, Any]) -> List[Dict[str, str]]:
    mode = source_cfg.get("mode", "modrinth")
    minecraft_version = server_cfg.get("minecraft_version")
    loader = server_cfg.get("loader", "fabric")
    installed: List[Dict[str, str]] = []

    if mode == "local_only":
        local_dir = ROOT / source_cfg.get("local_mods_dir", "local_mods")
        return copy_local_mods(output_dir, local_dir)

    for mod in mods_cfg.get("mods", []):
        if mod.get("source") != "modrinth":
            continue
        resolved = resolve_modrinth_mod(mod, minecraft_version, loader)
        if not resolved:
            if mod.get("required", False):
                raise RuntimeError(f"Could not resolve required mod: {mod.get('name', 'unknown')}")
            continue
        dest = output_dir / "mods" / resolved["filename"]
        download_file(resolved["url"], dest)
        installed.append({
            "name": resolved["name"],
            "filename": resolved["filename"],
            "source": "modrinth",
            "project_id": resolved["project_id"],
            "version_id": resolved["version_id"],
        })

    return installed


def build_manifest(output_dir: Path, server_cfg: Dict[str, Any], installed_mods: List[Dict[str, str]]) -> None:
    manifest = {
        "server": {
            "name": server_cfg.get("name"),
            "minecraft_version": server_cfg.get("minecraft_version"),
            "loader": server_cfg.get("loader"),
            "loader_version": server_cfg.get("loader_version"),
        },
        "mods": installed_mods,
        "notes": [
            "First version does not yet auto-download the server loader jar.",
            "Place the correct server jar in this folder as server.jar, or use Docker with a compatible image.",
        ],
    }
    write_text(output_dir / "manifest.json", json.dumps(manifest, indent=2))


def build_docker_files(output_dir: Path, server_cfg: Dict[str, Any]) -> None:
    compose = f"""services:
  minecraft:
    image: itzg/minecraft-server:latest
    container_name: minecraft-server
    ports:
      - \"{server_cfg.get('server_port', 25565)}:25565\"
    environment:
      EULA: \"TRUE\"
      TYPE: \"{server_cfg.get('loader', 'FABRIC').upper()}\"
      VERSION: \"{server_cfg.get('minecraft_version', '1.20.1')}\"
      MEMORY: \"{server_cfg.get('java_memory', {}).get('max', '4G')}\"
      MOTD: \"{server_cfg.get('motd', 'Minecraft Server')}\"
      DIFFICULTY: \"{server_cfg.get('difficulty', 'normal')}\"
      MODE: \"{server_cfg.get('gamemode', 'survival')}\"
      ENABLE_RCON: \"false\"
    tty: true
    stdin_open: true
    restart: unless-stopped
    volumes:
      - ./data:/data
      - ./mods:/data/mods
      - ./config:/data/config
"""
    dockerfile = """FROM itzg/minecraft-server:latest
"""
    write_text(output_dir / "docker-compose.yml", compose)
    write_text(output_dir / "Dockerfile", dockerfile)


def main() -> None:
    config = load_yaml(CONFIG_PATH)
    mods = load_yaml(MODS_PATH)
    server_cfg = config.get("server", {})
    source_cfg = config.get("mod_sources", {})
    packaging_cfg = config.get("packaging", {})

    output_dir = ROOT / packaging_cfg.get("output_dir", "output") / "server-bundle"
    ensure_clean_output(output_dir)

    write_text(output_dir / "eula.txt", f"eula={truthy(server_cfg.get('eula', True))}\n")
    write_text(output_dir / "server.properties", build_server_properties(server_cfg))
    build_start_scripts(output_dir, server_cfg)

    installed_mods = install_mods(output_dir, server_cfg, mods, source_cfg)
    build_manifest(output_dir, server_cfg, installed_mods)

    if packaging_cfg.get("include_docker", True):
        build_docker_files(output_dir, server_cfg)

    print(f"Server bundle created at: {output_dir}")
    print("Next step: add the correct server.jar or use the generated docker-compose.yml")


if __name__ == "__main__":
    main()
