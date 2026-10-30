# HW8 run guide (data260-4098)

Everything runs from the repo root on your Mac with `.venv` activated, except the four
Part 2 agent terminals (they run from `code/hw8/`, as the assignment shows).
Expected time: about 1 hour. 📸 marks a screenshot. Every script prints
"Kazi Samina Maraj Mumu" on its first line, so keep that line visible in each terminal
screenshot (scroll up or make the window tall enough).

---

## 0. One-time setup

```bash
cd ~/<path>/data260-4098
unzip -o ~/Downloads/hw8_files.zip -d .      # copies the HW8 files into the repo
source .venv/bin/activate
pip install -r requirements.txt               # adds aiokafka 0.12.0
make test-hw08                                # offline tests, expect 7/7 passed
```

* Docker Desktop must be running. Ollama must be running with `qwen3:8b` (Part 2 only).
* If an old Kafka container (for example the class demo container `kafka`) is running,
  stop it first, because port 9092 must be free: `docker ps`, then `docker stop kafka`.

---

## Part 1 - request/response over Kafka

### 1a. Start Kafka and create the topics

```bash
docker compose -f docker-compose.hw8.yml up -d kafka
docker compose -f docker-compose.hw8.yml ps        # wait until kafka is "healthy"
bash code/hw8/create_topics.sh
```
📸 **topics**: the `create_topics.sh` output (7 `s4098_` topics, and the describe output
that shows `s4098_tasks` with 2 partitions).

### 1b. Start the worker and the FastAPI wrapper

```bash
docker compose -f docker-compose.hw8.yml up -d --build worker api
docker ps
docker logs s4098-incident-worker
docker logs s4098-incident-api
```
📸 **docker ps**: shows `s4098-kafka`, `s4098-incident-worker`, `s4098-incident-api`.
📸 **worker log**: contains `Consumer is ready and listening...`.
📸 **API log**: contains `FastAPI server started at http://127.0.0.1:8498`.

(One terminal with these four commands one after another is enough, if all of it fits.)

### 1c. Run the demo

```bash
mkdir -p reports/hw08/raw/logs
python homework_demo.py 2>&1 | tee -a reports/hw08/RUN_LOG.txt
```
It prints steps 1-7 (CREATE), 8-9 (GET), 10 (the retrieved incident), and then the
**full sequence**: client, API and worker log lines merged in order for both
correlation_ids. It also saves `reports/hw08/raw/part1_sequence.log` and
`part1_demo.json`.

📸 **CREATE/GET**: the top part (operation, data, incident_id, success, correlation_id).
📸 **full sequence**: the merged CREATE -> GET log (send, receive, process, reply, client
response in order). Two screenshots are fine if it is long.

Optional extra evidence with curl (not required):
```bash
curl -s -X POST http://127.0.0.1:8498/incidents/kafka -H 'Content-Type: application/json' \
  -d '{"operation":"GET_INCIDENT","data":{"incident_id":"does-not-exist"}}'
```
-> `{"correlation_id": "...", "success": false, "error": "Incident not found"}`

---

## Part 2 - three agents over Kafka

Open four terminals, all with `source .venv/bin/activate` and `cd code/hw8`:

| Terminal | Command |
|---|---|
| 1 | `python planner.py 2>&1 \| tee ../../reports/hw08/raw/logs/part2_planner.log` |
| 2 | `python writer.py 2>&1 \| tee ../../reports/hw08/raw/logs/part2_writer.log` |
| 3 | `python reviewer.py 2>&1 \| tee ../../reports/hw08/raw/logs/part2_reviewer.log` |
| 4 | `python send_question.py 2>&1 \| tee -a ../../reports/hw08/RUN_LOG.txt` |

Wait until terminals 1-3 print `ASSIGNMENT partitions=...` before you start terminal 4.
qwen3:8b needs roughly 10-40 s for the whole journey.

📸 **planner / writer / reviewer**: one screenshot per terminal showing RECEIVE ->
PROCESS -> SEND -> COMMIT with the same correlation_id.
📸 **sender**: terminal 4 shows the journey (one line per stage with topic, partition,
offset, time) and the final JSON with `status` and `answer`.

The final message is also saved to `reports/hw08/raw/part2_final.json`.
When you are done, stop terminals 1-3 with Ctrl+C (Part 3 starts its own Writers).

---

## Part 3 - failure behavior

Each command prints the Writer's own log lines inline (prefixed with `|`), appends its
console output to `reports/hw08/RUN_LOG.txt`, and saves raw data in `reports/hw08/raw/`.
Take one 📸 per run (before and after), so 8-10 screenshots in total. If a run is long,
the important lines are the `[TEST]` lines plus the Writer lines around them.

### I. Duplicate delivery (Part 1 worker)

```bash
HW8_IDEMPOTENCY=off docker compose -f docker-compose.hw8.yml up -d worker
python code/hw8/run_failure_tests.py duplicate --mode before
HW8_IDEMPOTENCY=on docker compose -f docker-compose.hw8.yml up -d worker
python code/hw8/run_failure_tests.py duplicate --mode after
```
Before: 2 different incident_ids for one correlation_id (store size=2). After: the same
incident_id twice and a `DUPLICATE ... no new incident created` worker line.
📸 both runs.

Extra row (same idea in the agent pipeline, Writer replay):
```bash
python code/hw8/run_failure_tests.py duplicate-agent --mode before
python code/hw8/run_failure_tests.py duplicate-agent --mode after
```

### II. Consumer death

```bash
python code/hw8/run_failure_tests.py consumer-death --mode before --real-llm
python code/hw8/run_failure_tests.py consumer-death --mode after --real-llm
```
The Writer calls qwen3:8b and is killed with `kill -9` 2.5 s after it starts processing.
Before (auto-commit): the offset is already committed -> after the restart the message is
never redelivered, no draft (lost). After (commit after success): the offset is not
committed -> the restarted Writer receives the same offset again and finishes it.
If qwen3 is very fast and the kill comes too late, run it without `--real-llm`
(simulated 6 s of work instead).

**Independent check (use this for AI_USE question 2/3):** each run prints its consumer
group (`s4098_writers_death_after_<run>`). Ask Kafka itself, not my script:
```bash
docker exec s4098-kafka /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 --describe --group s4098_writers_death_after_<run>
```
📸 the `CURRENT-OFFSET` for the partition must equal the script's "at the end" value.

### III. Poison message

```bash
python code/hw8/run_failure_tests.py poison --mode before
python code/hw8/run_failure_tests.py poison --mode after
docker exec s4098-kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 --topic s4098_dead_letter --from-beginning --timeout-ms 5000
```
Before: the Writer retries the bad task forever and the good task behind it is never
processed. After: 3 attempts (0.5 s, 1 s backoff), then `DEAD-LETTER s4098_dead_letter`,
commit, and the good task is processed.
📸 both runs and the dead-letter consumer output.

### IV. Ordering (VERIFY_SEED = 264098)

```bash
python code/hw8/run_failure_tests.py ordering --mode before    # no key
python code/hw8/run_failure_tests.py ordering --mode after     # key = incident_id
```
Two Writers in one group, one partition each. The 20 messages (4 incidents x 5 status
updates) are generated from VERIFY_SEED. Before: every incident uses both partitions and
some updates are processed out of order. After: each incident stays in one partition and
every incident is processed 1,2,3,4,5.
📸 both runs (the "processing order" block). CSVs: `raw/ordering_before_nokey.csv`,
`raw/ordering_after_keyed.csv`.
(The no-key run depends on timing. With VERIFY_SEED it showed 3 inversions in my test
runs; if yours shows 0, run it again and keep both runs in RUN_LOG.)

### Failure table

```bash
python code/hw8/run_failure_tests.py summary
```

---

## Verify, metrics, commit, tag

```bash
docker compose -f docker-compose.hw8.yml up -d          # worker must have idempotency on
git add -A
git commit -m "HW8: Kafka request/response, three-agent pipeline, failure tests + results"
make verify-hw08                                         # expect 18/18
python code/hw8/build_metrics.py                         # writes reports/hw08/METRICS.md
```
📸 **verify**: the `make verify-hw08` output.

`make verify-hw08` records the commit it tested. Then add `AI_USE.md` (edit the draft),
the report PDF (`reports/hw08/report.pdf` and the Canvas copy `Mumu_HW8.pdf`), and:
```bash
git add -A
git commit -m "HW8 report, METRICS.md, AI_USE.md, verification.json"
git tag hw8
git push origin main --tags
git rev-parse 'refs/tags/hw8^{commit}'                  # put this in the Canvas comment
```

Finally stop everything: `docker compose -f docker-compose.hw8.yml down`.
