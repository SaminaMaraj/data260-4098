# Historical Part 3 and Part 5 runs (kept unchanged as evidence)

## Part 5

- `attacks_first_run/`: first attack run (2026-10-23). It saved no full traces,
  so the results could not be checked against the complete trace.
- `attacks_run2_injection_not_retrieved/`: second run. The full-trace check
  showed that the injected block ranked 4th in `policy_retriever`, so with the
  prompt defense (k=3) the model never saw it. The fixtures were changed so the
  injected block ranks first (with a test), and everything was run again. Only
  the third run (`../attacks.json`, `../attacks/`) is used in the report.

## Part 3

- `part3_before_hard_budget/`: the earlier Part 3 runs (used in my first submission and my first
  revised report). The
  token budget was only checked before each model call, so the last call of a
  run could go over it, and the reflection call was added afterwards. Part 3
  was re-run with the hard budget in `code/mcp/token_budget.py` (commit
  2e11986); only the rerun (`../reflexion_*.csv/json`, `../reflections.jsonl`)
  is used in the report.
