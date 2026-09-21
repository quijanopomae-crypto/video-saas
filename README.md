# CANONICAL-EXECUTABLE-BASELINE-v1.1

Origin: `BUILT_FROM_APPROVED_SPECIFICATION`.

This repository is the first machine-readable implementation of the approved BENCH100/model-manifest specification. It does **not** claim historical byte identity with prior chat documents.

Created: 2026-09-17T22:35:02.111009Z

Source documents are recorded by SHA-256 in `manifests/model-manifest-bench100-v1.1.yaml`.

Current state: `POST_PR13_STABILIZATION`; canonical planning and owner-scoped persistence are merged. Authentication/authorization is still required before the five-user pilot. Provider Preflight remains OFF.

Integrity result: `30/30 passed`; Asset Freeze remains `DEFERRED`; provider probes have not been executed.

Run integrity suite:

```bash
python -m pytest -q tests
```

No provider probes or spend are authorized. Provider Preflight and paid provider requests remain OFF until explicit owner authorization.

## Development infrastructure

The repository control plane is complete. The active development task builds the minimal product skeleton under `apps/api` and `apps/web` while Provider Preflight and paid provider requests remain disabled.

Windows-first commands:

```powershell
Copy-Item .env.example .env
.\scripts\dev.ps1
.\scripts\test.ps1
```

See `docs/DEVELOPMENT.md` for the local workflow.
