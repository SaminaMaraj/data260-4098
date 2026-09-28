# HW4 N+1 and Index Metrics

## Configuration

- SID4: 4098
- PORT_BASE: 8498
- PREFIX: s4098
- Database: s4098_rel
- Seed: 4098
- Requests per experiment: 30
- Total measurements: 180

## N+1 Benchmark Results

| Page size | Version | SQL statements/request | p50 (ms) | p95 (ms) | p99 (ms) |
|---:|---|---:|---:|---:|---:|
| 10 | naive | 13 | 5.301 | 7.174 | 9.310 |
| 10 | fixed | 4 | 2.742 | 4.234 | 11.572 |
| 50 | naive | 53 | 14.756 | 17.512 | 22.746 |
| 50 | fixed | 4 | 4.059 | 4.135 | 4.198 |
| 200 | naive | 203 | 51.222 | 61.845 | 66.399 |
| 200 | fixed | 4 | 11.463 | 13.144 | 21.862 |

## Interpretation

The naive implementation performs one additional related-data query for each incident. Therefore, its SQL statements increase from 13 to 53 to 203 as the page size grows from 10 to 50 to 200.

The fixed implementation uses eager loading or a join and remains at four SQL statements per request. It avoids hundreds of individual related-data queries.

For page size 200, the fixed version reduces p50 latency from 51.222 ms to 11.463 ms, approximately a 77.6% reduction.

## Index Evidence

Index added:

```text
ix_incidents_category
```

Before the index:

```text
type=ALL
key=NULL
rows=4885
```

After the index:

```text
type=ref
key=ix_incidents_category
rows=1256
```

The query changed from a full table scan to an indexed lookup. The estimated number of rows examined decreased from 4,885 to 1,256.

The complete EXPLAIN outputs are stored in:

```text
reports/hw04/raw/explain_before.txt
reports/hw04/raw/explain_after.txt
```