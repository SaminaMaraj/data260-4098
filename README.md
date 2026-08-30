# DATA 260 Homework 1

Municipal transit incident reporting web application and local agent pipeline.

## Personal configuration

| Value | Result |
|---|---|
| SID4 | 4098 |
| PORT_BASE | 8498 |
| PREFIX | s4098 |
| SEED | 4098 |
| VERIFY_SEED | 264098 |
| DOMAIN_ID | 2 |
| Assigned domain | Municipal transit incidents |
| Hardware | Apple Silicon Mac M5, 24 GB RAM |
| Local model | qwen3:8b |
| Python | 3.12.10 |
| Tagged commit | Add after creating the `hw1` tag |
| Repository URL | Add after creating the GitHub repository |

## Project structure

- `code/web_application/` — HTML, CSS, and JavaScript application
- `code/agents_demo.py` — Planner, Reviewer, and Finalizer pipeline
- `code/run_nondeterminism.py` — 40-run experiment
- `code/hw1_client.py` — interactive code-review client
- `src/model_client.py` — reusable Ollama model adapter
- `reports/hw01/cases/` — fixed experiment input
- `reports/hw01/raw/` — raw experiment data and screenshots
- `reports/hw01/METRICS.md` — experiment and token metrics
- `reports/hw01/AI_USE.md` — AI-use disclosure
- `AGENT.md` — bullet-only code-review instructions
- `DOMAIN_SCHEMA.md` — municipal transit incident schema

## Python setup

Run from the repository root:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
ollama pull qwen3:8b

```

Ensure the Ollama application is running.

## Run the web application locally with Docker

Run from the repository root:

```bash
docker build --platform linux/amd64 -t data260-4098-web ./code
docker run -d --platform linux/amd64 --name data260-4098-container -p 8498:80 data260-4098-web
```

Open `http://localhost:8498`.

Stop the container afterward:

```bash
docker stop data260-4098-container
```

## Run the agent pipeline

```bash
python code/agents_demo.py \
  --model qwen3:8b \
  --title "Bus Delay at Santa Clara Station" \
  --content "The VTA Route 22 bus arrived thirty minutes late at Santa Clara Station and affected passengers during the afternoon commute." \
  --email "kazisaminamaraj.mumu@sjsu.edu" \
  --temperature 0.0 \
  --strict
```

## Part 2 answers

### Q1. Final tags

- `vta route`
- `santa clara station`
- `clara station`

### Q2. Final summary

VTA Route 22 bus delay at Santa Clara Station disrupted afternoon commuters by
30 minutes.

### Q3. Did the Reviewer change anything?

Yes. The Reviewer changed the Planner's first tag from
`santa clara station commute` to `vta route delay`, making it more directly
related to the affected transit route. It retained the concise summary.

### Agent flow

- Planner proposes three topical tags and a short summary from the input.
- Reviewer checks topical relevance, formatting, and the 25-word limit.
- Finalizer produces the final strict JSON.
- Schema coercion guarantees exactly three tags and a summary of at most 25 words.
- The publish package adds the original fields, transcript, result, and timestamp.

## Run the non-determinism experiment

The script uses the unchanged input in
`reports/hw01/cases/nondeterminism_input.json`.

```bash
python code/run_nondeterminism.py
```

On macOS, prevent sleep during the experiment with:

```bash
caffeinate -i python code/run_nondeterminism.py
```

The 40 results are saved in
`reports/hw01/raw/nondeterminism_runs.json`. Results are documented in
`reports/hw01/METRICS.md`.

## Run the Part 4 client

```bash
python code/hw1_client.py
```

Commands:

- `/stats` — show turn count, cumulative tokens, and history length
- `/exit` — exit and print cumulative statistics

Per-turn token data is saved in
`reports/hw01/raw/token_counts.json`.

## Part 4 written answers

### Why is prior conversation context resent with every turn?

A model request is stateless. The application resends the system prompt and
previous messages so the model can reconstruct the conversation.

### How is a system prompt different from a user message?

A system prompt defines the model's role, behavior, and output rules. A user
message contains the current request or information to process.

### Why do input tokens grow over a conversation?

Each turn adds a user message and assistant response. The expanding history is
resent with the next request, so input-token counts increase.

### What eventually limits that growth?

The model's context-window limit eventually restricts how much history can be
sent. Applications must truncate, summarize, or selectively retain messages.

## Verification

Run from the repository root:

```bash
python code/verify_hw01.py
```

The output is saved in `reports/hw01/verification.json`.

## Reports

See `reports/hw01/` for the run log, raw data, metrics, AI-use disclosure,
verification output, and final report.