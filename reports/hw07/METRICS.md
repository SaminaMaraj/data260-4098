# HW7 Metrics - Kazi Samina Maraj Mumu (SID4 4098)

Model: qwen3:8b via Ollama · Hardware: Apple MacBook Pro M5, 24 GB · commit: `<fill after tag>`

> Fill every `…` from the printed summaries in RUN_LOG.txt and the files in `raw/`.

## Part 2 - Tool-call reliability (21 attempts, 7 × tasks A/B/C)

Settings: temperature `…`, max_iterations 8, max_repairs 2. Raw: `raw/reliability_attempts.csv`, `raw/reliability_summary.json`.

| Measure | Value |
|---|---|
| Tool-use opportunities | … |
| Well-formed call rate **before** repair | … |
| Well-formed call rate **after** repair | … |
| Attempts clean before repair | … / 21 |
| Attempts well-formed after repair | … / 21 |
| Task success (verifier) | … / 21 |

| Failure type | Count | Attempts affected |
|---|---|---|
| Malformed arguments | … | … |
| Unknown tool | … | … |
| Text when a tool was required | … | … |
| Lost multi-step chain | … | … |

## Part 3 - Original loop vs Reflexion (same 3 tasks × `…` repeats)

Raw: `raw/reflexion_comparison.csv`, `raw/reflexion_summary.json`, `raw/reflections.jsonl`.

| Metric | Original loop | Reflexion loop |
|---|---|---|
| Task success | … | … |
| Unsupported claims | … | … |
| Retry rate | … | … |
| Tool calls (mean) | … | … |
| Tokens (mean) | … | … |
| Latency (ms, mean) | … | … |
| Verifier false rejections | … | … |

## Part 4 - Bay Wheels scenarios

| Scenario | Rows | Riders | Pay-per-use | Membership total | Decision | Steps | Time | Stop reason |
|---|---|---|---|---|---|---|---|---|
| A (membership should win) | … | … | … | … | … | … | … | … |
| B (pay-per-use should win) | … | … | … | … | … | … | … | … |

Pricing snapshot: URL `…`, accessed `…`, SHA-256 `…` (`raw/bikeshare/scenario_*/pricing_snapshot.*`).

## Part 5 - Prompt-injection attacks (scenario B, local fixtures)

Raw: `raw/attacks.json`, `raw/attacks.csv`.

| Attack | Before defenses | After prompt defense | After prompt + tool defense |
|---|---|---|---|
| Recommendation override | … | … | … |
| Non-SELECT tool misuse | … | … | … |
| Data exfiltration | … | … | … |

## Part 6 - Safety gate (10 commands)

Raw: `raw/safety_gate_results.csv`. Final: … / 10 correct (5 allowed, 5 blocked).
False allow found and fixed: `find . -name '*.pyc' -delete` (allowed by the v1 deny-list).
