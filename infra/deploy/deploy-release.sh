#!/usr/bin/env bash
set -euo pipefail

release_dir="$1"

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
