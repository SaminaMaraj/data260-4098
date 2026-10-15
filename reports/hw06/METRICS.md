# HW6 Memory Metrics

The experiment used 30-message conversations with four memory settings:
SHORT_TERM_N=4, SHORT_TERM_N=12, SHORT_TERM_N=30, and eviction_keep_12.

| Setting | Mean prompt tokens | Mean completion tokens | Mean latency (ms) | Mean probe quality | Estimated cost for 10,000 conversations |
|---|---:|---:|---:|---:|---:|
| SHORT_TERM_N=4 | 544.10 | 47.53 | 5222.00 | 3.00 | 234.525 |
| SHORT_TERM_N=12 | 761.20 | 39.33 | 5837.97 | 3.00 | 287.355 |
| SHORT_TERM_N=30 | 1087.83 | 41.80 | 6425.51 | 3.40 | 389.049 |
| eviction_keep_12 | 1087.83 | 41.80 | 11627.23 | 3.40 | 389.049 |

## Findings

SHORT_TERM_N=30 produced the highest probe quality with a score of 3.4, but it used the most prompt tokens and had a higher estimated cost. SHORT_TERM_N=4 was the least expensive and had the lowest latency, but its probe quality was 3.0. The experiment selected SHORT_TERM_N=30 as the best setting based on probe quality and SHORT_TERM_N=12 as the worst setting according to the script's comparison rule.

The eviction experiment had the same token and quality values as SHORT_TERM_N=30 but had substantially higher latency. This suggests that eviction added processing overhead without improving the measured probe score in this run.