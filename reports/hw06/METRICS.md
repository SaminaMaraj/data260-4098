# HW6 Metrics

## Memory-size experiment

Each setting used the same 30-message conversation in a fresh session, followed by the same five memory probes.

| Setting | Mean prompt tokens | Mean completion tokens | Mean latency (ms) | Mean probe quality | Estimated cost per 10,000 conversations |
|---|---:|---:|---:|---:|---:|
| SHORT_TERM_N=4 | 544.10 | 47.53 | 5211.51 | 3.0 | $234.525 |
| SHORT_TERM_N=12 | 761.20 | 39.33 | 5359.90 | 3.0 | $287.355 |
| SHORT_TERM_N=30 | 1087.83 | 41.80 | 6444.42 | 3.4 | $389.049 |
| eviction_keep_12 | 761.20 | 39.33 | 5643.06 | 3.0 | $287.355 |

## Cost formula

Estimated cost was calculated from the mean prompt and completion tokens, multiplied by 10,000 conversations and the assignment's token-price assumptions.

## Selection

SHORT_TERM_N=30 had the highest probe quality at 3.4. SHORT_TERM_N=4 was the lowest-cost and fastest setting, with probe quality of 3.0.

The eviction policy keeps the full conversation history in MongoDB but limits the short-term messages inserted into the prompt to 12 messages. This reduces prompt size while preserving the stored history.