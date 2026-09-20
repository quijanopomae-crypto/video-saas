# Lab

`lab/` is the experimental area for VIDEO-SAAS.

Code here is deliberately **non-canonical**. It exists so product ideas can be implemented, tested and rejected quickly without contaminating `apps/api` or `apps/web`.

## Rules

1. Canonical code under `apps/**` must never import from `lab/**`.
2. An experiment must declare its hypothesis, scope, acceptance criteria and promotion state.
3. Provider credentials and paid calls are forbidden unless a later Task Contract explicitly authorizes them.
4. Passing tests does not automatically make an experiment canonical.
5. Promotion requires:
   - the experiment tests to pass;
   - Repository Control CI to pass;
   - Product CI to remain green;
   - explicit user approval;
   - a new promotion Task Contract that moves the accepted design into `apps/**`.

The first experiment is `experiments/product-flow-001`.
