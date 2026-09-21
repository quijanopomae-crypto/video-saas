# CANONICAL-EXECUTABLE-BASELINE-v1.1

Origin: `BUILT_FROM_APPROVED_SPECIFICATION`.

This repository is the first machine-readable implementation of the approved BENCH100/model-manifest specification. It does **not** claim historical byte identity with prior chat documents.

Created: 2026-09-17T22:35:02.111009Z

Source documents are recorded by SHA-256 in `manifests/model-manifest-bench100-v1.1.yaml`.

Current state: `POST_PR13_STABILIZATION_PASS`; canonical planning and owner-scoped persistence are merged. Audit remediation is in progress. Authentication/authorization is implemented in the remediation branch and remains subject to CI/integration before the five-user pilot. Provider Preflight remains OFF.

Integrity result: `30/30 passed`; Asset Freeze remains `DEFERRED`; provider probes have not been executed.

Run integrity suite:

```bash
python -m pytest -q tests
```

No provider probes or spend are authorized. Provider Preflight and paid provider requests remain OFF until explicit owner authorization.

## Development infrastructure

The repository control plane, development infrastructure, canonical planning API and owner-scoped persistence are complete. No later product gate is currently authorized. Authentication/authorization remains mandatory before the five-user pilot, and Provider Preflight and paid provider requests remain disabled.

Windows-first commands:

```powershell
Copy-Item .env.example .env
.\scripts\dev.ps1
.\scripts\test.ps1
```

See `docs/DEVELOPMENT.md` for the local workflow.


## Operational state vs frozen baseline

Strings such as `READY_FOR_PROVIDER_PREFLIGHT` inside frozen manifests describe the experimental baseline only. They never authorize an operational action. Operational NEXT_ACTION authority comes from `PROJECT_STATE.yaml`, the active Task Contract when present, and `.state/`.
