#!/usr/bin/env bash
set -euo pipefail

release_dir="$1"

# ── Wait for cloud-init and apt locks ────────────────────────────────────────
# On a freshly provisioned server, cloud-init may still be running apt-get.
# Wait for it to finish before we attempt any package operations.
if command -v cloud-init >/dev/null 2>&1; then
    echo "Waiting for cloud-init to complete..."
    cloud-init status --wait 2>/dev/null || true
fi

# Belt-and-suspenders: wait for dpkg/apt lock files to be released.
echo "Waiting for apt/dpkg locks to clear..."
for i in $(seq 1 24); do
    if ! lsof /var/lib/apt/lists/lock /var/lib/dpkg/lock /var/lib/dpkg/lock-frontend 2>/dev/null | grep -q .; then
        break
    fi
    echo "  Lock held — waiting (${i}/24)..."
    sleep 5
done

# ── Ensure Docker + Compose plugin are available ─────────────────────────────
if ! command -v docker >/dev/null 2>&1; then
    echo "Docker not found — installing..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
fi

if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose plugin not found — installing..."
    apt-get update -qq
    apt-get install -y -qq docker-compose-plugin
fi

base_dir="/opt/minecraft-server"
shared_dir="${base_dir}/shared"
current_link="${base_dir}/current"

install -d -m 0755 "${base_dir}/releases"
install -d -m 0755 "${shared_dir}/data" "${shared_dir}/backups" "${shared_dir}/config" "${shared_dir}/mods" "${shared_dir}/logs"

rsync -a --delete "${release_dir}/mods/" "${shared_dir}/mods/"
rsync -a "${release_dir}/config/" "${shared_dir}/config/" || true
cp -f "${release_dir}/server.properties" "${shared_dir}/config/server.properties"
cp -f "${release_dir}/eula.txt" "${shared_dir}/config/eula.txt"
cp -f "${release_dir}/docker-compose.digitalocean.yml" "${shared_dir}/config/docker-compose.digitalocean.yml"
cp -f "${release_dir}/.env" "${shared_dir}/config/.env"

ln -sfn "${release_dir}" "${current_link}"

cd "${shared_dir}/config"
docker compose --env-file .env -f docker-compose.digitalocean.yml pull
docker compose --env-file .env -f docker-compose.digitalocean.yml up -d

# basic verification
sleep 5
docker compose --env-file .env -f docker-compose.digitalocean.yml ps
