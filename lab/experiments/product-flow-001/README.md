# product-flow-001

This experiment validates the first provider-independent product flow:

```text
ProjectRequest
  -> Project Bible
  -> Scene Graph
  -> Shot Contracts
  -> Preview Plan
```

It does **not** try to generate a good creative script with AI. Its purpose is to prove stable contracts, referential integrity, deterministic planning and exact duration accounting before provider models are connected.

Run:

```bash
python -m unittest discover -s tests -v
python run_demo.py fixtures/project_request.json
```

A successful experiment remains non-canonical until an explicit promotion task is approved.
