# HW9 run guide (data260-4098)

Everything runs from the repo root on your Mac with `.venv` activated.
Every script prints **"Kazi Samina Maraj Mumu"** on its first line — keep that line
visible in each terminal screenshot (make the window tall or take two screenshots).
📸 marks a screenshot for the report. Total time: about 1.5–2 hours, most of it waiting
for qwen3:8b in Part 3.2 and Part 4.

---

## 0. One-time setup (10 min)

```bash
cd ~/<path>/data260-4098
unzip -o ~/Downloads/hw9_files.zip -d .        # copies the HW9 files into the repo
source .venv/bin/activate
pip install -r requirements.txt                 # adds redis==6.4.0
make test-hw09                                  # offline tests, expect 7/7 passed
```

Start the three services:

```bash
docker start data260-4098-mysql                         # s4098_rel (MySQL, port 3308, .env DATABASE_URL)
docker compose -f docker-compose.hw9.yml up -d          # Redis Stack -> localhost:6380
docker compose -f docker-compose.hw9.yml ps             # wait for "healthy"
ollama list                                             # qwen3:8b must be there, Ollama app running
```

* If the image tag `redis/redis-stack:7.4.0-v3` cannot be pulled, change it in
  `docker-compose.hw9.yml` to `redis/redis-stack:latest`.
* Plain Redis (`redis:7`) is **not** enough: Part 2 needs the vector index (FT.CREATE / KNN).
* RedisInsight (optional) at http://localhost:8001 shows the `s4098:*` keys.

**Commit the labeled test set before any sweep** (the assignment requires this):

```bash
git add reports/hw09/cases/cache_cases.yaml
git commit -m "HW9: labeled semantic-cache test set (frozen before the sweep)"
```

Then commit the rest of the code too (`git add src/hw9_cache src/hw9_agents code/hw9 tests/test_hw09.py docker-compose.hw9.yml HW9_RUN_GUIDE.md Makefile pyproject.toml requirements.txt`).

---

## Part 1 — view counter (2 min)

```bash
mkdir -p reports/hw09
python code/hw9/part1_view_counter.py 2>&1 | tee reports/hw09/RUN_LOG.txt
```

The first run adds the column `incidents.view_count` to s4098_rel (printed once).
📸 **counter**: `=== Testing Counter ===`, Access #1 … #25 with the two
`✓ Synced views to database` lines after #10 and #20, then Redis = 25 / DB = 20 and the timing lines.

Optional extra proof (same terminal):
```bash
docker exec -it s4098-redis redis-cli GET s4098:views:incident:42
```

---

## Part 2 — semantic cache, 12 queries (3–5 min)

```bash
python code/hw9/part2_semantic_cache.py 2>&1 | tee -a reports/hw09/RUN_LOG.txt
```

Misses go through the HW8 Planner → Writer → Reviewer functions with qwen3:8b
(grounded with facts from s4098_rel). Hits come from Redis.
📸 **part2 log**: a few query blocks showing `CACHE MISS best_similarity=…` and
`CACHE HIT similarity=… matched=…` lines.
📸 **part2 summary**: the summary table + hit rate + average latency cached vs non-cached.

Optional: run it through the real Kafka agents instead (Kafka + the three HW8 agent terminals
from HW8_RUN_GUIDE.md must be running): add `--agent-path kafka`.

---

## Part 3 — threshold sweep, false hit, stale answers

### 3.2 Sweep (≈ 30–45 min)

```bash
caffeinate -i python code/hw9/part3_threshold_sweep.py 2>&1 | tee -a reports/hw09/RUN_LOG.txt
```

It first produces the 10 seed answers once, then runs the 40 cases at 0.75, 0.80, 0.85,
0.90 and 0.95. Each threshold is saved separately; if it stops, run the same command again
and it continues with the missing thresholds.
📸 **sweep table**: the final `=== Threshold sweep (40 cases) ===` table.
📸 **sweep log**: one screenshot of the per-case lines of one threshold (e.g. 0.85),
showing `false_hit` / `correct_hit` / `correct_miss` outcomes.

### 3.5 Stale answer + invalidation (1–2 min)

```bash
python code/hw9/part3_stale_demo.py 2>&1 | tee -a reports/hw09/RUN_LOG.txt
```

📸 **stale demo**: steps [1]–[5]: first answer (operator VTA) → UPDATE in s4098_rel →
stale HIT with the old answer → `STALE entry … data_version … -> invalidate` → fresh answer →
hit with the fresh answer. The script restores the record at the end.

---

## Part 4 — self-improving two-agent system (≈ 25–40 min)

```bash
python code/hw9/part4_self_improving.py demo-revision 2>&1 | tee -a reports/hw09/RUN_LOG.txt
python code/hw9/part4_self_improving.py all           2>&1 | tee -a reports/hw09/RUN_LOG.txt
```

`all` = train (creates lessons) → validate (keeps/rejects each lesson) → reuse-demo → test
(four variants on test_data.json).

📸 **4.1 revision**: the `--- Revision sequence ---` block (question, initial answer,
evaluator result + feedback, revised answer, final evaluation, number of attempts, final response).
📸 **4.2 lesson created**: the training lines with `** LESSON CREATED lesson_00x …`.
📸 **4.2 lesson reused**: the `=== 4.2 Lesson reuse on a later related question ===` block
(`LESSON LOADED …`, result, use_count).
📸 **4.3 gate**: the `GATE lesson_00x … => KEEP/REJECT` lines and `Kept lessons`.
📸 **4.4 table**: the final `=== 4.4 Results on test_data.json ===` table.

---

## Finish

```bash
python code/hw9/build_metrics.py          # writes reports/hw09/METRICS.md from raw/
git add reports/hw09 code/hw9/part4_datasets/lessons.json
git commit -m "HW9: results"
git tag hw9 && git push && git push origin hw9
```

Then send Claude: `reports/hw09/` as a zip (RUN_LOG.txt, METRICS.md, raw/) and your
screenshots — the report PDF is written from those real numbers.

### If something fails

| Symptom | Fix |
|---|---|
| `unknown command 'FT._LIST'` / `unknown index name` errors | You are on plain Redis; use the Redis Stack container (port 6380). |
| `Error 61 connecting to localhost:6380` | `docker compose -f docker-compose.hw9.yml up -d` |
| `KeyError: 'DATABASE_URL'` | run from the repo root (`.env` must be there) and start MySQL. |
| Ollama timeout | `export OLLAMA_TIMEOUT=180` and run the command again. |
| Sweep interrupted | run the same command again; finished thresholds are skipped. |
