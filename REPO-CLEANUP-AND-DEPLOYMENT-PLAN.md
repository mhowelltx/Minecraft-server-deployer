# Repo Cleanup and Deployment Plan

## Goal

Make **Fabric** the default/main supported path first, then add **Forge/NeoForge bootstrap** as first-class options, then stand up a cloud test deployment path so server bundles can be validated in an environment close to production.

---

## Phase 0 — Baseline and guardrails (1–2 days)

1. **Define supported scope in one place**
   - Document target Minecraft versions, loader support order, and support policy.
   - Mark Fabric as GA path; Forge/NeoForge as planned.

2. **Establish consistency checks**
   - Add a small CI matrix that runs:
     - `python -m compileall scripts`
     - smoke tests for config parsing and manifest generation.
   - Add a changelog/release notes workflow so behavior changes are tracked.

3. **Create acceptance criteria for each loader path**
   - “Bootstrap succeeds”, “mods resolve”, “bundle starts locally”, “manifest complete”.

---

## Phase 1 — Make Fabric the default main path (2–4 days)

1. **Unify script entrypoint**
   - Introduce a single CLI entrypoint (`scripts/build_server.py`) that routes by loader.
   - Set default loader to Fabric when unspecified.
   - Keep explicit loader override (`fabric`, `forge`, `neoforge`, `vanilla`) in config.

2. **Refactor shared logic to common module(s)**
   - Move shared functions out of loader-specific scripts:
     - YAML loading
     - server.properties/eula generation
     - mod download + local copy
     - output directory scaffolding
     - manifest + Docker file generation
   - Keep only loader-bootstrap logic per loader implementation.

3. **Reduce duplication and naming confusion**
   - Retire duplicate behavior between `build_server.py` and `build_fabric_server.py`.
   - Keep backward-compatible wrappers temporarily:
     - old scripts call new entrypoint and print deprecation notice.

4. **Align docs to the new default**
   - README quickstart should call a single command.
   - Fabric bootstrap doc becomes implementation detail / deep dive.

5. **Fabric validation**
   - Add automated smoke test:
     - run build on sample config
     - assert launcher jar chosen
     - assert expected files exist (`start.sh`, `manifest.json`, `docker-compose.yml`).

**Deliverable:** one canonical build command where Fabric is default and fully validated.

---

## Phase 2 — Add Forge and NeoForge bootstrap (3–6 days)

1. **Introduce loader plugin interface**
   - Define a simple bootstrap contract, e.g.:
     - `bootstrap(loader_config, output_dir) -> bootstrap_metadata`
   - Implement plugins:
     - `bootstrap_fabric.py`
     - `bootstrap_forge.py`
     - `bootstrap_neoforge.py`

2. **Forge bootstrap implementation**
   - Resolve Forge installer by MC version (prefer stable/recommended logic).
   - Download installer + run headless server install.
   - Determine launch artifact and write start scripts.

3. **NeoForge bootstrap implementation**
   - Resolve NeoForge installer/version mapping by MC version.
   - Download + install server runtime.
   - Detect launch artifact/classpath and generate correct start scripts.

4. **Loader-aware mod validation**
   - Preflight-check mod compatibility based on loader + MC version.
   - Add clear warnings/errors for mismatches before download.

5. **Per-loader test matrix in CI**
   - Smoke test each loader path with minimal fixture config.
   - Validate manifest captures loader-specific metadata and versions.

**Deliverable:** Fabric/Forge/NeoForge are selectable through one entrypoint and pass CI smoke builds.

---

## Phase 3 — Packaging and release hardening (2–4 days)

1. **Bundle integrity and reproducibility**
   - Add checksums in `manifest.json` for downloaded artifacts.
   - Optionally lock resolved mod versions into a lockfile.

2. **Operational defaults**
   - Add env override support for memory, JVM flags, port, world name.
   - Add basic server health/readiness checks for containerized runs.

3. **Release artifact strategy**
   - Publish built bundle as CI artifact.
   - Optional: publish container image variant tagged by loader + MC version.

---

## Phase 4 — Cloud test deployment path (MVP first) (3–7 days)

### Recommended MVP target: Azure Container Apps or AWS ECS Fargate

Pick one first for speed; keep infra code provider-agnostic where possible.

1. **Infra as code**
   - Create `infra/` with Terraform for:
     - container runtime service
     - persistent volume/storage
     - secrets/config
     - network ingress/port mapping

2. **CI/CD environment pipeline**
   - On merge to `main`:
     - build bundle
     - package runtime image (or upload bundle)
     - deploy to ephemeral test environment
     - run smoke checks (port open, startup log markers)

3. **Test automation in cloud**
   - Post-deploy checks:
     - process starts successfully
     - world data persisted across restart
     - basic joinability check from probe container/script

4. **Observability and rollback**
   - Enable logs + metrics forwarding.
   - Add one-click rollback to previous known-good deploy.

**Deliverable:** automatic deployment to a cloud test environment with startup and persistence verification.

---

## Phase 5 — Production readiness follow-ups (optional)

- Secrets hardening and least-privilege IAM.
- Cost controls (auto-stop schedules, lower env sizes).
- Backup/restore for world data.
- Player auth/RCON admin model.
- Multi-environment promotion flow (dev → staging → production).

---

## Suggested implementation sequence (quickest risk burn-down)

1. Unify entrypoint + Fabric default.
2. Extract common code into shared modules.
3. Add loader plugin contract.
4. Implement Forge bootstrap.
5. Implement NeoForge bootstrap.
6. Add CI matrix for all loaders.
7. Add cloud MVP deployment (single provider first).
8. Add observability + rollback.

---

## Definition of done for your request

- Fabric is the default path in docs + CLI behavior.
- Forge and NeoForge are bootstrapped via same workflow.
- CI validates all loader paths with smoke tests.
- One cloud environment can deploy/test bundles automatically.
