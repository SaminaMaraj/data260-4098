# HW7 run guide (data260-4098)

Everything runs from the repo root on your Mac, with `.venv` activated.
Expected total time with qwen3:8b: about 1.5–2 hours, mostly waiting on the model.
📸 marks the moments to take a screenshot. Keep your name visible in every terminal
window; each script prints it at the top.

---

## 0. One-time setup

```bash
cd ~/<path>/data260-4098
unzip -o ~/Downloads/hw7_files.zip -d .     # copies the HW7 files into the repo
source .venv/bin/activate
pip install -r requirements.txt               # adds PyJWT, ruff 0.15.6, pre-commit
docker start data260-4098-mysql               # MySQL (port 3308)
ollama serve  # (or open the Ollama app) and make sure qwen3:8b is pulled
```

Add these lines to your **git-ignored** `.env`, choosing your own passwords:

```bash
python -c "import secrets; print(secrets.token_hex(32))"   # paste as JWT_SECRET_KEY
```
```
JWT_SECRET_KEY=<the 64 hex chars>
HW7_READER_PASSWORD=<pick one>
HW7_WRITER_PASSWORD=<pick one>
HW7_MODERATOR_PASSWORD=<pick one>
```

Offline sanity check (no model needed, takes seconds):
```bash
make test-hw07          # expect 9/9, 9/9, 8/8 passed
```

---

## Part 1 - JWT, roles, MySQL, Ruff

```bash
PYTHONPATH=. python code/migrate_hw07.py
```
This adds `username` + `role` (with a CHECK constraint) to `users` and creates
`s4098_reader`, `s4098_writer` and `s4098_moderator` with PBKDF2 hashes. Its printout
shows the table with truncated hashes, which you can use as evidence that no plain-text
passwords are stored.

Start the API:
```bash
PYTHONPATH=. python -m uvicorn src.api:app --port 8498
```

Postman requests (`{{base}}` = `http://localhost:8498`, body = raw JSON):

| # | Request | Expect | 📸 |
|---|---|---|---|
| 1 | `POST {{base}}/auth/login` `{"username":"s4098_writer","password":"…"}` | 200 + `access_token` | login OK |
| 2 | same with a wrong password | 401 | login fail |
| 3 | `GET {{base}}/auth/me`, no Authorization header | 401 | me no token |
| 4 | `GET {{base}}/auth/me`, header `Authorization: Bearer <expired>` | 401 "Token has expired" | expired token |
| 5 | `POST {{base}}/api/hw4/incidents` with the **reader** token | 403 | reader create |
| 6 | same with the **writer** token | 201 | writer create |
| 7 | `DELETE {{base}}/api/hw4/incidents/<id from 6>` with the writer token | 403 | writer delete |
| 8 | same with the **moderator** token | 200 | moderator delete |
| 9 | `GET {{base}}/api/hw4/incidents?limit=5` with any token | 200 | list |

* For #4, get a correctly signed but expired token with
  `PYTHONPATH=. python code/hw07_expired_token.py`. (`Bearer abc.def.ghi` returns
  401 "Invalid token" if you also want to show an invalid token.)
* Body for #5/#6:
  `{"incidentCode":"INC-970001","incidentTitle":"HW7 role test","routeLine":"VTA Route 22","routeId":1,"submitterEmail":"writer@example.com","description":"Created to test JWT role-based access control.","category":"delay","passengersAffected":1,"termsAccepted":true}`
* The React app (`cd frontend && npm run dev`) now logs in with the username and sends
  the Bearer token.

**Lint demo** (one terminal screenshot, or a short series). Stage the HW7 work and commit:
```bash
pre-commit install
git add -A
git commit -m "HW7: JWT auth with roles, agent loop, Reflexion, bikeshare agent, file tools"
```
The hook **fails on `src/api.py`**, an older file of yours. Ruff auto-fixes the
import order (I001), `ruff-format` reformats the file, and one error stays: **E501**
(line too long) at the `description="Light rail service was interrupted…"` line.
Fix it by splitting the string:
```python
        description=(
            "Light rail service was interrupted because of a "
            "track maintenance issue."
        ),
```
Then commit again:
```bash
git add -A && git commit -m "HW7: JWT auth with roles, agent loop, Reflexion, bikeshare agent, file tools"
```
All hooks pass. 📸 the failing run, the fix, and the passing commit.

---

## Part 2 - Hand-written agent loop (≈15–25 min)

```bash
python code/mcp/run_hw07_part2.py tasks          # A, B, C + error recovery
python code/mcp/run_hw07_part2.py reliability    # 21 attempts, temperature 0.7
```
📸 tasks A, B and C (tool-call lines + final answer + `verifier: passed=True`) and the
error-recovery block (`error=incident not found`, then a clean answer). 📸 the
RELIABILITY SUMMARY. The code snippet for the report is `run_agent` in
`code/mcp/agent_loop.py`.

The reliability run uses temperature 0.7 for all 21 attempts. At 0.0 all 21 attempts
would be identical, so the rate would say nothing about reliability.

---

## Part 3 - Reflexion (≈20–30 min)

```bash
python code/mcp/run_hw07_part3.py --repeats 3
```
This prints the comparison table, and its numbers go into METRICS.md. Then check two
things:
* `reports/hw07/raw/reflections.jsonl` must contain at least one reflection (a failed,
  then retried attempt). If qwen passed every task, run again with
  `--repeats 5 --temperature 1.0`. Don't edit results by hand.
* Verifier false rejections: look at rows with `verifier_false_rejection=True` in
  `raw/reflexion_comparison.csv` and decide by hand whether the answer was actually
  correct (for example, a code written as "incident 123" instead of "INC-000123"). Write a
  2–3 sentence note on it. If there are none, say so.

---

## Part 4 - Bay Wheels agent (≈10 min + downloads)

1. Download one recent monthly file from https://s3.amazonaws.com/baywheels-data/index.html
   (for example `202509-baywheels-tripdata.csv.zip`) into a `data/` folder (git-ignored).
2. Build both scenarios from the real rows:
   ```bash
   python code/hw07_build_scenarios.py data/202509-baywheels-tripdata.csv.zip
   ```
3. With the API running, open **http://localhost:8498/hw7/bikeshare**. Upload
   `reports/hw07/raw/scenarios/scenario_A_membership.csv`, set the label to `scenario_A`
   and click Run. 📸 the full page. Repeat with `scenario_B_payg.csv` and label
   `scenario_B`. 📸

Each run saves `reports/hw07/raw/bikeshare/<label>/run.json`, `pricing_snapshot.txt`
(the exact page text) and `pricing_snapshot.json` (URL, access time, SHA-256).
**If the pricing URL fails** (an error in the timeline), open the Bay Wheels pricing page
in your browser and use *Save Page As → Web Page, HTML only* to save it as
`reports/hw07/fixtures/baywheels_pricing_saved.html`. Then use the URL
`http://localhost:8498/hw7/fixtures/baywheels_pricing_saved.html` and mention this in
the report.

---

## Part 5 - Prompt injection (≈15–20 min)

```bash
python code/run_hw07_attacks.py
```
This runs 3 attacks × 3 configurations on scenario B and prints the before/after table.
📸 it. For the report, take one excerpt per cell from the `outcome:` lines. The threat
model draft is in `reports/hw07/THREAT_MODEL.md`.

---

## Part 6 - File tools + safety gate (≈1 min)

```bash
python code/run_hw07_file_tools.py
```
📸 the whole output. It shows (a) glob → search → read finding `beta.py` and (b) the
10-command table with the v1 column, the false allow on
`find . -name '*.pyc' -delete`, and the final 10/10.

---

## Finish

```bash
git add -A && git commit -m "HW7 results and evidence"
make verify-hw07                      # writes reports/hw07/verification.json
git add reports/hw07/verification.json && git commit -m "HW7 verification"
git tag hw7 && git push origin main --tags
```
Then fill in `METRICS.md`, edit `AI_USE.md` so it matches what you actually did, and
put the PDF at `reports/hw07/Mumu_HW7.pdf`. Send me your outputs and screenshots and
I'll draft the report text.
