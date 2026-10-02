# Part 3 - Domain Tool Contracts

The following rejected calls are the real Part 2B Inspector results. Each
domain tool uses the shared `{ok, data, error}` response envelope.

## `search_incidents`

| Expected JSON input schema | Rejected JSON input | Returned error output | Why it was rejected |
|---|---|---|---|
| `{"query": string, "category": string|null, "limit": integer 1-50}` | `{"query":"delay","category":"unknown-category","limit":10}` | `{"ok":false,"data":null,"error":"unknown category: unknown-category"}` | The category is not one of `delay`, `collision`, `service-suspension`, or `infrastructure-issue`. |

## `get_incident`

| Expected JSON input schema | Rejected JSON input | Returned error output | Why it was rejected |
|---|---|---|---|
| `{"incident_code": string matching ^INC-\\d{6}$}` | `{"incident_code":"abc"}` | `{"ok":false,"data":null,"error":"incident_code must match INC-######"}` | The incident code does not have the required `INC-` prefix followed by six digits. |

## `incident_count_by_route`

| Expected JSON input schema | Rejected JSON input | Returned error output | Why it was rejected |
|---|---|---|---|
| `{"min_incidents": integer >= 0}` | `{"min_incidents":-5}` | `{"ok":false,"data":null,"error":"min_incidents must be greater than or equal to 0"}` | A minimum incident count cannot be negative. |

## Retry policy

- Maximum retries after the first attempt: `2`.
- Maximum total attempts: `3`.
- Base delay: `0.05` seconds.
- Exponential delay: `0.05`, then `0.10` seconds.
- Maximum delay cap: `0.20` seconds.
- Per-attempt timeout: `2.0` seconds.
- Fault-injection seed: `264098`.
