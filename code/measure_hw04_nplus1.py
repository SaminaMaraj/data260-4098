import json
from collections import defaultdict
from pathlib import Path
from time import perf_counter

from fastapi.testclient import TestClient
from sqlalchemy import event

from src.api import app
from src.hw4_database import engine


OUTPUT_DIR = Path("reports/hw04/raw")
PAGE_SIZES = [10, 50, 200]
VERSIONS = ["naive", "fixed"]
REPETITIONS = 30


def percentile(values, percent):
    values = sorted(values)
    index = round((percent / 100) * (len(values) - 1))
    return round(values[index], 3)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    client = TestClient(app)

    login_response = client.post(
        "/api/hw4/auth/login",
        json={
            "email": "samina.hw4@example.com",
            "password": "Transit4098!",
        },
    )

    if login_response.status_code != 200:
        raise RuntimeError(
            f"Login failed: {login_response.status_code} "
            f"{login_response.text}"
        )

    query_counter = [0]

    def count_queries(*args, **kwargs):
        query_counter[0] += 1

    event.listen(engine, "before_cursor_execute", count_queries)

    measurements = []

    try:
        for version in VERSIONS:
            for page_size in PAGE_SIZES:
                for request_number in range(1, REPETITIONS + 1):
                    query_counter[0] = 0

                    url = (
                        f"/api/hw4/benchmark/incidents/{version}"
                        f"?page_size={page_size}&page=0"
                    )

                    start = perf_counter()
                    response = client.get(url)
                    latency_ms = (perf_counter() - start) * 1000

                    payload = response.json()
                    records = payload.get("records", [])

                    measurements.append(
                        {
                            "version": version,
                            "page_size": page_size,
                            "request_number": request_number,
                            "status_code": response.status_code,
                            "row_count": len(records),
                            "sql_statements": query_counter[0],
                            "latency_ms": round(latency_ms, 3),
                        }
                    )
    finally:
        event.remove(engine, "before_cursor_execute", count_queries)

    output_file = OUTPUT_DIR / "nplus1_measurements.jsonl"

    with output_file.open("w") as file:
        for row in measurements:
            file.write(json.dumps(row) + "\n")

    grouped = defaultdict(list)

    for row in measurements:
        key = (row["version"], row["page_size"])
        grouped[key].append(row)

    summaries = []

    for (version, page_size), rows in sorted(grouped.items()):
        latencies = [row["latency_ms"] for row in rows]
        queries = [row["sql_statements"] for row in rows]

        summaries.append(
            {
                "version": version,
                "page_size": page_size,
                "requests": len(rows),
                "rows_per_response": rows[0]["row_count"],
                "sql_statements_per_request": round(
                    sum(queries) / len(queries), 2
                ),
                "p50_ms": percentile(latencies, 50),
                "p95_ms": percentile(latencies, 95),
                "p99_ms": percentile(latencies, 99),
            }
        )

    summary_file = OUTPUT_DIR / "nplus1_summary.json"
    summary_file.write_text(json.dumps(summaries, indent=2))

    print(f"Saved {len(measurements)} measurements.")
    print(f"Saved: {output_file}")
    print(f"Saved: {summary_file}")

    for summary in summaries:
        print(summary)


if __name__ == "__main__":
    main()