# Minecraft Server Deployer

Config-driven Fabric Minecraft server bundle builder with a GitHub Actions + Terraform + DigitalOcean deployment path.

## Architecture

This repository separates responsibilities into three layers:

1. **Provisioning**
   - Terraform (`infra/terraform`) provisions DigitalOcean infrastructure.
   - Resources: droplet, firewall, optional volume, optional SSH key registration.
2. **Configuration / bootstrap**
   - cloud-init (`infra/cloud-init/minecraft-server.yaml`) configures first boot:
     - installs Docker + Compose plugin
     - creates runtime directories under `/opt/minecraft-server`
3. **Deployment**
   - GitHub Actions deploy workflow uploads the Fabric bundle to a timestamped release directory and flips `/opt/minecraft-server/current`.
   - Docker Compose (`infra/deploy/docker-compose.digitalocean.yml`) runs the Fabric server.

## Current scope

- ✅ Fabric-first implementation
- ✅ DigitalOcean VM provisioning
- ✅ Cloud-init bootstrap
- ✅ Docker Compose runtime
- ✅ Persistent server data kept on VM
- ⏳ Forge/NeoForge automation: not implemented in this task

## Runtime layout on server

```text
/opt/minecraft-server/
  current -> /opt/minecraft-server/releases/<release-id>
  releases/
    <release-id>/
  shared/
    data/       # world + runtime data persisted across deploys
    backups/
    config/     # server.properties, eula.txt, compose file, env file
    mods/       # deployed mod set
    logs/
```

Release bundles are immutable snapshots. Persistent Minecraft data is **not** stored in GitHub artifacts.

## Prerequisites

- A DigitalOcean account/token
- Repository admin access to configure GitHub secrets/variables
- At least one SSH key fingerprint in DigitalOcean (or supply public keys via Terraform variable)

## Required GitHub Secrets

- `DIGITALOCEAN_ACCESS_TOKEN` (required): DigitalOcean API token
- `SSH_PRIVATE_KEY` (required): private key used by deploy workflow to SSH into the server
- `SSH_KNOWN_HOSTS` (optional): precomputed known_hosts entry for strict host checking

## Optional GitHub Variables

- `DO_SSH_KEY_FINGERPRINTS_JSON` (optional, recommended): either a JSON list of existing DigitalOcean SSH key fingerprints (for example `["fp1","fp2"]`) or a single fingerprint string.
- `DO_SSH_KEY_FINGERPRINTS_JSON` (optional, recommended): JSON list of existing DigitalOcean SSH key fingerprints.

Terraform also supports registering SSH public keys directly via `ssh_public_keys` if you prefer that route.

## Infrastructure (Terraform)

Location: `infra/terraform/`

### Provisioned resources

- `digitalocean_droplet`
- `digitalocean_firewall`
- `digitalocean_volume` (optional)
- `digitalocean_volume_attachment` (optional)
- `digitalocean_ssh_key` (optional registration from provided public keys)

### Important variables

- `server_name`
- `server_size`
- `image`
- `region`
- `volume_size`
- `enable_volume`
- `ssh_key_fingerprints`
- `allowed_ssh_cidrs`
- `allowed_minecraft_cidrs`

### Terraform outputs

- `server_public_ipv4`
- `server_name`
- `volume_id` (null when no volume)

## Workflows

### 1) Build bundle

Workflow: `.github/workflows/build-fabric-server-pack.yml`

- Builds a Fabric server bundle from `server-config.yaml` + `mods.yaml`
- Uploads artifact `minecraft-fabric-server-bundle`

### 2) Provision infrastructure

Workflow: `.github/workflows/provision-digitalocean.yml`

Manual `workflow_dispatch` inputs include:

- `environment` (`dev`/`prod`)
- `server_name`
- `server_size`
- `region`
- `image`
- `enable_volume`
- `volume_size`
- `allowed_ssh_cidrs`
- `allowed_minecraft_cidrs`
- `auto_apply`

Behavior:

- Terraform `init`, `validate`, `plan`, `apply`
- Stores state and output JSON as an artifact for starter-style single-repo usage

### 3) Deploy release

Workflow: `.github/workflows/deploy-digitalocean.yml`

Manual `workflow_dispatch` inputs include:

- `environment`
- `artifact_source` (`build` or `latest_artifact`)
- optional `run_id` (for specific artifact run)
- `ssh_user`

Behavior:

- Builds or downloads Fabric bundle
- Loads server IP from Terraform outputs artifact
- Uploads bundle to `/opt/minecraft-server/releases/<timestamp-sha>`
- Syncs release config/mods into `/opt/minecraft-server/shared`
- Updates `/opt/minecraft-server/current` symlink
- Runs Docker Compose from shared config path
- Keeps world data in `/opt/minecraft-server/shared/data` across redeploys

### 4) Destroy infrastructure (optional)

Workflow: `.github/workflows/destroy-digitalocean.yml`

- Manual run with confirmation string `DESTROY`
- Destroys resources using Terraform state artifact

## Recommended workflow order (first run)

1. Configure required GitHub secrets (`DIGITALOCEAN_ACCESS_TOKEN`, `SSH_PRIVATE_KEY`; optional `SSH_KNOWN_HOSTS`).
2. (Optional) Set `DO_SSH_KEY_FINGERPRINTS_JSON` repository variable.
3. Run **Provision DigitalOcean Infrastructure** with your desired environment inputs.
4. Run **Deploy to DigitalOcean** with `artifact_source=build` for first deployment.
5. Verify server process/container status and connect via Minecraft client.

## Redeploy behavior and persistence

On each deploy:

- A new release directory is uploaded.
- `/opt/minecraft-server/current` is atomically switched.
- `mods`, `config`, `server.properties`, and `eula.txt` are synced to `shared` runtime paths.
- Docker Compose is restarted from shared config.
- World data in `/opt/minecraft-server/shared/data` is preserved.

## Assumptions and notes

- This starter setup stores Terraform state as a GitHub artifact for simplicity.
- For stronger production guarantees, migrate Terraform backend to remote state with locking.
- Optional DigitalOcean volume is provisioned/attached; cloud-init currently keeps runtime under `/opt/minecraft-server/shared` on root disk unless you add mount migration logic.
- Existing generic builder path remains in repo; Fabric path is kept as the deployment default for safety.

## Next cleanup step (safe follow-up)

- Consolidate `scripts/build_server.py` and `scripts/build_fabric_server.py` behind one CLI entrypoint, with Fabric as default, after adding regression tests for current Fabric behavior.
Config-driven Minecraft server pack builder with Docker support, mod manifest support, and a GitHub Actions workflow for push-button packaging.

## Planning

See the staged repo cleanup and deployment plan here:

- [REPO-CLEANUP-AND-DEPLOYMENT-PLAN.md](REPO-CLEANUP-AND-DEPLOYMENT-PLAN.md)
