#!/usr/bin/env python3
"""Build a runnable Fabric Minecraft server bundle from YAML config."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "server-config.yaml"
MODS_PATH = ROOT / "mods.yaml"
MODPACK_PATH = ROOT / "modpack.yaml"
USER_AGENT = "minecraft-server-deployer/fabric-bootstrap-0.1"
MODRINTH_PROJECT_API = "https://api.modrinth.com/v2/project/{project_id}/version"
FABRIC_INSTALLER_VERSIONS = "https://meta.fabricmc.net/v2/versions/installer"
FABRIC_INSTALLER_MAVEN = "https://maven.fabricmc.net/net/fabricmc/fabric-installer/{version}/fabric-installer-{version}.jar"
CURSEFORGE_API_BASE = "https://api.curseforge.com/v1"


def load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def ensure_clean_output(output_dir: Path) -> None:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    for rel in ["mods", "config", "logs", "world", "data"]:
        (output_dir / rel).mkdir(parents=True, exist_ok=True)


def truthy(value: Any) -> str:
    return "true" if bool(value) else "false"


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def make_executable(path: Path) -> None:
    current = path.stat().st_mode
    path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


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
        f"force-gamemode={truthy(server_cfg.get('force_gamemode', False))}",
        f"white-list={truthy(server_cfg.get('white_list', False))}",
        f"spawn-protection={server_cfg.get('spawn_protection', 0)}",
        f"server-port={server_cfg.get('server_port', 25565)}",
        f"level-seed={server_cfg.get('level_seed', '')}",
    ]
    return "\n".join(lines) + "\n"


def download_file(url: str, destination: Path) -> None:
    with requests.get(url, stream=True, headers={"User-Agent": USER_AGENT}, timeout=60) as response:
        response.raise_for_status()
        with destination.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    handle.write(chunk)


def choose_launcher_jar(output_dir: Path) -> str:
    for candidate in ["fabric-server-launch.jar", "server.jar"]:
        if (output_dir / candidate).exists():
            return candidate
    return "fabric-server-launch.jar"


def build_start_scripts(output_dir: Path, server_cfg: Dict[str, Any]) -> str:
    min_mem = server_cfg.get("java_memory", {}).get("min", "2G")
    max_mem = server_cfg.get("java_memory", {}).get("max", "4G")
    launcher = choose_launcher_jar(output_dir)

    linux_script = f"""#!/usr/bin/env bash
set -euo pipefail
cd \"$(dirname \"$0\")\"
java -Xms{min_mem} -Xmx{max_mem} -jar {launcher} nogui
"""
    windows_script = f"""@echo off
cd /d %~dp0
java -Xms{min_mem} -Xmx{max_mem} -jar {launcher} nogui
pause
"""
    write_text(output_dir / "start.sh", linux_script)
    write_text(output_dir / "start.bat", windows_script)
    make_executable(output_dir / "start.sh")
    return launcher


def copy_local_mods(output_dir: Path, local_mods_dir: Path) -> List[Dict[str, str]]:
    installed: List[Dict[str, str]] = []
    if not local_mods_dir.exists():
        return installed
    for item in sorted(local_mods_dir.iterdir()):
        if item.is_file() and item.suffix.lower() == ".jar":
            dest = output_dir / "mods" / item.name
            shutil.copy2(item, dest)
            installed.append({"name": item.name, "source": "local", "filename": item.name})
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

    requested_filename = mod.get("filename")
    chosen_file = None
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


def install_mods(output_dir: Path, server_cfg: Dict[str, Any], mods_cfg: Dict[str, Any], source_cfg: Dict[str, Any]) -> List[Dict[str, str]]:
    mode = source_cfg.get("mode", "modrinth")
    minecraft_version = server_cfg.get("minecraft_version")
    loader = "fabric"
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


def require_java() -> None:
    try:
        subprocess.run(["java", "-version"], check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("Java is required to bootstrap a Fabric server but was not found in PATH.") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("Java appears to be installed but failed to run.") from exc


def resolve_latest_fabric_installer() -> str:
    response = requests.get(FABRIC_INSTALLER_VERSIONS, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()
    versions = response.json()
    if not versions:
        raise RuntimeError("Could not resolve a Fabric installer version.")
    stable = [item for item in versions if item.get("stable")]
    chosen = stable[0] if stable else versions[0]
    return str(chosen["version"])


def bootstrap_fabric_server(output_dir: Path, server_cfg: Dict[str, Any]) -> Dict[str, str]:
    require_java()
    minecraft_version = server_cfg.get("minecraft_version")
    loader_version = server_cfg.get("loader_version")
    installer_version = resolve_latest_fabric_installer()

    installer_path = output_dir / f"fabric-installer-{installer_version}.jar"
    installer_url = FABRIC_INSTALLER_MAVEN.format(version=installer_version)
    download_file(installer_url, installer_path)

    command = [
        "java",
        "-jar",
        installer_path.name,
        "server",
        "-mcversion",
        str(minecraft_version),
        "-loader",
        str(loader_version),
        "-downloadMinecraft",
    ]
    subprocess.run(command, cwd=output_dir, check=True)

    launch_jar = choose_launcher_jar(output_dir)
    return {
        "installer_version": installer_version,
        "loader_version": str(loader_version),
        "launcher": launch_jar,
    }


def build_manifest(output_dir: Path, server_cfg: Dict[str, Any], installed_mods: List[Dict[str, str]], bootstrap: Dict[str, Any], launcher: str) -> None:
    manifest = {
        "server": {
            "name": server_cfg.get("name"),
            "minecraft_version": server_cfg.get("minecraft_version"),
            "loader": "fabric",
            "loader_version": server_cfg.get("loader_version"),
            "launcher": launcher,
        },
        "bootstrap": bootstrap,
        "mods": installed_mods,
        "notes": ["Fabric server bootstrap completed successfully."],
    }
    write_text(output_dir / "manifest.json", json.dumps(manifest, indent=2))


def build_docker_files(output_dir: Path, server_cfg: Dict[str, Any]) -> None:
    compose_lines = [
        "services:",
        "  minecraft:",
        "    image: itzg/minecraft-server:latest",
        "    container_name: minecraft-server",
        "    ports:",
        f"      - \"{server_cfg.get('server_port', 25565)}:25565\"",
        "    environment:",
        "      EULA: \"TRUE\"",
        "      TYPE: \"FABRIC\"",
        f"      VERSION: \"{server_cfg.get('minecraft_version', '1.20.1')}\"",
        f"      FABRIC_LOADER_VERSION: \"{server_cfg.get('loader_version', '0.15.11')}\"",
        f"      MEMORY: \"{server_cfg.get('java_memory', {}).get('max', '4G')}\"",
        f"      MOTD: \"{server_cfg.get('motd', 'Minecraft Server')}\"",
        f"      DIFFICULTY: \"{server_cfg.get('difficulty', 'normal')}\"",
        f"      MODE: \"{server_cfg.get('gamemode', 'survival')}\"",
        "      ENABLE_RCON: \"false\"",
        "    tty: true",
        "    stdin_open: true",
        "    restart: unless-stopped",
        "    volumes:",
        "      - ./data:/data",
        "      - ./mods:/data/mods",
        "      - ./config:/data/config",
        "      - ./server.properties:/data/server.properties",
        "      - ./eula.txt:/data/eula.txt",
    ]
    write_text(output_dir / "docker-compose.yml", "\n".join(compose_lines) + "\n")
    write_text(output_dir / "Dockerfile", "FROM itzg/minecraft-server:latest\n")


def load_modpack_config() -> Optional[Dict[str, Any]]:
    """Return modpack.yaml contents, or None if the file does not exist."""
    if not MODPACK_PATH.exists():
        return None
    return load_yaml(MODPACK_PATH)


def _cf_headers(api_key: str) -> Dict[str, str]:
    return {"x-api-key": api_key, "User-Agent": USER_AGENT}


def resolve_curseforge_project_id(slug: str, game_id: int, api_key: str) -> int:
    """Resolve a CurseForge project slug to a numeric project ID."""
    url = f"{CURSEFORGE_API_BASE}/mods/search"
    params = {"gameId": game_id, "slug": slug}
    response = requests.get(url, params=params, headers=_cf_headers(api_key), timeout=30)
    response.raise_for_status()
    results = response.json().get("data", [])
    if not results:
        raise RuntimeError(f"CurseForge: no project found for slug '{slug}' (gameId={game_id}).")
    return int(results[0]["id"])


def _get_curseforge_file_info(project_id: int, file_id: int, api_key: str) -> Dict[str, Any]:
    url = f"{CURSEFORGE_API_BASE}/mods/{project_id}/files/{file_id}"
    response = requests.get(url, headers=_cf_headers(api_key), timeout=30)
    response.raise_for_status()
    return response.json()["data"]


def _get_latest_curseforge_file(project_id: int, api_key: str) -> Dict[str, Any]:
    url = f"{CURSEFORGE_API_BASE}/mods/{project_id}/files"
    params = {"pageSize": 1, "sortField": 5, "sortOrder": "desc"}  # sortField 5 = DateCreated
    response = requests.get(url, params=params, headers=_cf_headers(api_key), timeout=30)
    response.raise_for_status()
    files = response.json().get("data", [])
    if not files:
        raise RuntimeError(f"CurseForge: no files found for project {project_id}.")
    return files[0]


def download_curseforge_modpack_zip(
    project_id: int, file_id: Optional[int], api_key: str, dest_path: Path
) -> None:
    """Download a CurseForge modpack ZIP to dest_path."""
    if file_id:
        file_info = _get_curseforge_file_info(project_id, file_id, api_key)
    else:
        file_info = _get_latest_curseforge_file(project_id, api_key)

    download_url = file_info.get("downloadUrl")
    if not download_url:
        raise RuntimeError(
            f"CurseForge: no downloadUrl for project {project_id} file {file_info.get('id')}. "
            "The file may be distribution-restricted."
        )
    download_file(download_url, dest_path)


def install_curseforge_modpack(
    output_dir: Path, modpack_cfg: Dict[str, Any], api_key: str
) -> List[Dict[str, str]]:
    """
    Download the Beyond Depth (or any CurseForge) modpack, parse its manifest,
    download every mod JAR, and copy the overrides folder into the bundle.
    Returns a list of installed mod dicts compatible with the existing manifest schema.
    """
    slug = modpack_cfg["slug"]
    game_id = int(modpack_cfg.get("game_id", 432))
    raw_file_id = modpack_cfg.get("file_id", "")
    file_id: Optional[int] = int(raw_file_id) if raw_file_id else None

    print(f"Resolving CurseForge project ID for slug '{slug}'...")
    project_id = resolve_curseforge_project_id(slug, game_id, api_key)
    print(f"  -> project ID: {project_id}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        zip_path = tmp_path / "modpack.zip"

        print(f"Downloading modpack ZIP (project={project_id}, file={file_id or 'latest'})...")
        download_curseforge_modpack_zip(project_id, file_id, api_key, zip_path)

        with zipfile.ZipFile(zip_path, "r") as zf:
            # Extract manifest.json
            manifest_bytes = zf.read("manifest.json")
            manifest: Dict[str, Any] = json.loads(manifest_bytes)

            # Copy overrides/ (configs, datapacks, etc.) into the bundle root
            overrides_prefix = manifest.get("overrides", "overrides") + "/"
            for member in zf.namelist():
                if member.startswith(overrides_prefix) and not member.endswith("/"):
                    rel = member[len(overrides_prefix):]
                    dest = output_dir / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, dest.open("wb") as dst:
                        shutil.copyfileobj(src, dst)

    # Download each mod listed in the manifest
    installed: List[Dict[str, str]] = []
    mod_entries: List[Dict[str, Any]] = manifest.get("files", [])
    total = len(mod_entries)
    print(f"Downloading {total} mods from modpack manifest...")

    for idx, entry in enumerate(mod_entries, start=1):
        mod_project_id = entry["projectID"]
        mod_file_id = entry["fileID"]
        required = entry.get("required", True)

        try:
            file_info = _get_curseforge_file_info(mod_project_id, mod_file_id, api_key)
            download_url = file_info.get("downloadUrl")
            filename = file_info.get("fileName", f"{mod_project_id}-{mod_file_id}.jar")

            if not download_url:
                raise RuntimeError("no downloadUrl (distribution-restricted)")

            dest = output_dir / "mods" / filename
            download_file(download_url, dest)
            installed.append({
                "name": file_info.get("displayName", filename),
                "filename": filename,
                "source": "curseforge",
                "project_id": str(mod_project_id),
                "version_id": str(mod_file_id),
            })
            print(f"  [{idx}/{total}] {filename}")
        except Exception as exc:
            if required:
                raise RuntimeError(
                    f"Failed to download required mod (project={mod_project_id}, file={mod_file_id}): {exc}"
                ) from exc
            print(f"  [{idx}/{total}] SKIP optional mod project={mod_project_id}: {exc}")

    print(f"Modpack install complete: {len(installed)}/{total} mods downloaded.")
    return installed


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
    bootstrap = bootstrap_fabric_server(output_dir, server_cfg)
    bootstrap["status"] = "ok"

    modpack_config = load_modpack_config()
    if modpack_config and modpack_config.get("modpack", {}).get("source") == "curseforge":
        api_key = os.environ.get("CURSEFORGE_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "CURSEFORGE_API_KEY environment variable is required for modpack installation. "
                "Obtain a free key at https://console.curseforge.com and set it before running."
            )
        installed_mods = install_curseforge_modpack(output_dir, modpack_config["modpack"], api_key)
    else:
        installed_mods = install_mods(output_dir, server_cfg, mods, source_cfg)

    launcher = build_start_scripts(output_dir, server_cfg)

    if packaging_cfg.get("include_docker", True):
        build_docker_files(output_dir, server_cfg)

    build_manifest(output_dir, server_cfg, installed_mods, bootstrap, launcher)
    print(f"Server bundle created at: {output_dir}")
    print(f"Launcher jar: {launcher}")
    print("Fabric bootstrap completed.")


if __name__ == "__main__":
    main()
