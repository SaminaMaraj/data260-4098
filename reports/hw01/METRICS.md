# HW01 Metrics

## Part 3 — Measuring Non-Determinism

The experiment used the unchanged input saved in
`reports/hw01/cases/nondeterminism_input.json`.

Each temperature was tested 20 times with `qwen3:8b`. Tag-set comparisons
ignored tag order. Latency percentiles used linear interpolation.

### Tag variation

| Metric | Temperature 0.7 | Temperature 0.0 |
|---|---:|---:|
| Number of runs | 20 | 20 |
| Distinct tag sets | 9 | 1 |
| Tags appearing in all 20 runs | None | `clara station`, `santa clara`, `vta route` |
| Tags appearing in exactly one run | `santa clara station delay` | None |

### Latency

| Metric | Temperature 0.7 | Temperature 0.0 |
|---|---:|---:|
| p50 | 95,109 ms | 95,638 ms |
| p95 | 151,817 ms | 96,491 ms |
| p99 | 181,604 ms | 99,873 ms |

### Interpretation

At temperature 0.7, two users submitting the same input could receive
different but related tags because the 20 runs produced nine distinct tag
sets. At temperature 0.0, all 20 runs produced the same tag set, so users
would see a more consistent result.

Variation is acceptable when suggesting descriptive search tags for a
transit incident because several relevant labels can describe the same
event. Variation is not acceptable when assigning a safety-critical incident
severity or emergency response priority because inconsistent classifications
could change the required response.

## Part 4 — Token Accounting

| Turn | Input tokens | Output tokens | Total tokens | Cumulative input | Cumulative output | History length | Bullet-only |
|---:|---:|---:|---:|---:|---:|---:|:---:|
| 1 | 112 | 935 | 1,047 | 112 | 935 | 588 | Yes |
| 2 | 142 | 497 | 639 | 254 | 1,432 | 985 | Yes |
| 3 | 231 | 357 | 588 | 485 | 1,789 | 1,463 | Yes |
| 4 | 339 | 740 | 1,079 | 824 | 2,529 | 2,184 | Yes |
| 5 | 503 | 448 | 951 | 1,327 | 2,977 | 2,698 | Yes |

### `/stats` snapshots

| After turn | Turn count | Cumulative input | Cumulative output | History length |
|---:|---:|---:|---:|---:|
| 3 | 3 | 485 | 1,789 | 1,463 |
| 5 | 5 | 1,327 | 2,977 | 2,698 |

All five responses followed the strict bullet-only instructions in
`AGENT.md`. Input-token counts increased because the system prompt and prior
conversation history were resent with each new model request.