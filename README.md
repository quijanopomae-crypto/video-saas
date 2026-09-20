# CANONICAL-EXECUTABLE-BASELINE-v1.1

Origin: `BUILT_FROM_APPROVED_SPECIFICATION`.

This repository is the first machine-readable implementation of the approved BENCH100/model-manifest specification. It does **not** claim historical byte identity with prior chat documents.

Created: 2026-09-17T22:35:02.111009Z

Source documents are recorded by SHA-256 in `manifests/model-manifest-bench100-v1.1.yaml`.

Current state: `READY_FOR_PROVIDER_PREFLIGHT`.

Integrity result: `30/30 passed`; Asset Freeze remains `DEFERRED`; provider probes have not been executed.

Run integrity suite:

```bash
python -m pytest -q tests
```

No provider probes or spend are authorized until integrity passes.
