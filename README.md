# CANONICAL-EXECUTABLE-BASELINE-v1.1

Origin: `BUILT_FROM_APPROVED_SPECIFICATION`.

This repository is the first machine-readable implementation of the approved BENCH100/model-manifest specification. It does **not** claim historical byte identity with prior chat documents.

Created: 2026-09-17T22:35:02.111009Z

Source documents are recorded by SHA-256 in `manifests/model-manifest-bench100-v1.1.yaml`.

Current state: `AUDIT_REMEDIATION`; canonical planning, owner-scoped persistence, and authenticated server-side owner authorization are merged. The final reproducibility/CI hardening and durable IDLE close are in progress. Provider Preflight remains OFF.

Integrity result: `30/30 passed`; Asset Freeze remains `DEFERRED`; provider probes have not been executed.

Run integrity suite:

```bash
python -m pytest -q tests
```

No provider probes or spend are authorized. Provider Preflight and paid provider requests remain OFF until explicit owner authorization.

## Development infrastructure

The repository control plane, development infrastructure, canonical planning API, owner-scoped persistence, and authenticated owner authorization are complete. No later product gate is authorized by this remediation. Authentication/authorization must remain enabled for the five-user pilot, and Provider Preflight and paid provider requests remain disabled.

Windows-first commands:

```powershell
Copy-Item .env.example .env
.\scripts\dev.ps1
.\scripts\test.ps1
```

See `docs/DEVELOPMENT.md` for the local workflow.


## Operational state vs frozen baseline

Strings such as `READY_FOR_PROVIDER_PREFLIGHT` inside frozen manifests describe the experimental baseline only. They never authorize an operational action. Operational NEXT_ACTION authority comes from `PROJECT_STATE.yaml`, the active Task Contract when present, and `.state/`.
