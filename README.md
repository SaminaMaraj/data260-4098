# DATA 260 Coursework

Municipal transit incident reporting application and local agent workflows for DATA 260.

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
| HW1 tagged commit | `74943c714f0dd2eaabc0e169529008a1c68dffb7` (`hw1`) |
| Repository URL | https://github.com/SaminaMaraj/data260-4098 |

## Project structure

- `code/web_application/` - responsive HTML, CSS, and JavaScript application
- `code/agents_demo.py` - HW1 Planner, Reviewer, and Finalizer pipeline
- `code/run_nondeterminism.py` - HW1 non-determinism experiment
- `code/hw1_client.py` - HW1 interactive code-review client
- `code/agents_graph.py` - HW2 stateful LangGraph supervisor workflow
- `code/run_hw2_experiments.py` - resumable HW2 experiment runner
- `src/api.py` - FastAPI CRUD and search backend
- `src/model_client.py` - reusable Ollama model adapter
- `reports/hw01/` - HW1 report, metrics, raw results, and evidence
- `reports/hw02/cases/` - frozen HW2 experiment inputs
- `reports/hw02/raw/` - raw HW2 experiment data and screenshots
- `reports/hw02/METRICS.md` - HW2 experiment metrics
- `reports/hw02/AI_USE.md` - HW2 AI-use disclosure
- `AGENT.md` - bullet-only code-review instructions
- `DOMAIN_SCHEMA.md` - municipal transit incident schema

## Python setup

Run from the repository root:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
ollama pull qwen3:8b
```

Ensure the Ollama application is running before using the agent workflows.

## Homework 1

### Run the web application locally with Docker

Run from the repository root:

```bash
docker build --platform linux/amd64 -t data260-4098-web ./code
docker run -d --platform linux/amd64 \
  --name data260-4098-container \
  -p 8498:80 \
  data260-4098-web
```

Open http://localhost:8498.

Stop the container afterward:

```bash
docker stop data260-4098-container
```

### Run the HW1 agent pipeline

```bash
python code/agents_demo.py \
  --model qwen3:8b \
  --title "Bus Delay at Santa Clara Station" \
  --content "The VTA Route 22 bus arrived thirty minutes late at Santa Clara Station and affected passengers during the afternoon commute." \
  --email "kazisaminamaraj.mumu@sjsu.edu" \
  --temperature 0.0 \
  --strict
```

### HW1 Part 2 answers

#### Q1. Final tags

- `vta route`
- `santa clara station`
- `clara station`

#### Q2. Final summary

VTA Route 22 bus delay at Santa Clara Station disrupted afternoon commuters by 30 minutes.

#### Q3. Did the Reviewer change anything?

Yes. The Reviewer changed the Planner's first tag from `santa clara station commute`
to `vta route delay`, making it more directly related to the affected transit route.
It retained the concise summary.

#### Agent flow

- The Planner proposes three topical tags and a short summary from the input.
- The Reviewer checks topical relevance, formatting, and the 25-word limit.
- The Finalizer produces the final strict JSON.
- Schema coercion guarantees exactly three tags and a summary of at most 25 words.
- The publish package adds the original fields, transcript, result, and timestamp.

### Run the HW1 non-determinism experiment

The script uses the unchanged input in
`reports/hw01/cases/nondeterminism_input.json`.

```bash
caffeinate -i python code/run_nondeterminism.py
```

The 40 results are saved in `reports/hw01/raw/nondeterminism_runs.json`.
Results are documented in `reports/hw01/METRICS.md`.

### Run the HW1 interactive client

```bash
python code/hw1_client.py
```

Commands:

- `/stats` - show turn count, cumulative tokens, and history length
- `/exit` - exit and print cumulative statistics

Per-turn token data is saved in `reports/hw01/raw/token_counts.json`.

### HW1 Part 4 written answers

#### Why is prior conversation context resent with every turn?

A model request is stateless. The application resends the system prompt and
previous messages so the model can reconstruct the conversation.

#### How is a system prompt different from a user message?

A system prompt defines the model's role, behavior, and output rules. A user
message contains the current request or information to process.

#### Why do input tokens grow over a conversation?

Each turn adds a user message and assistant response. The expanding history is
resent with the next request, so input-token counts increase.

#### What eventually limits that growth?

The model's context-window limit eventually restricts how much history can be
sent. Applications must truncate, summarize, or selectively retain messages.

### Verify HW1

```bash
python code/verify_hw01.py
```

The output is saved in `reports/hw01/verification.json`.

## Homework 2

Homework 2 extends the municipal transit application with a responsive interface,
a FastAPI CRUD backend, a stateful LangGraph workflow, Pydantic schema validation,
and loop-safety experiments.

### Run the FastAPI application

Run from the repository root:

```bash
source .venv/bin/activate
python -m uvicorn src.api:app --host 127.0.0.1 --port 8498 --reload
```

Open http://localhost:8498.

The application supports:

- Viewing all incident records
- Searching by incident title or transit route
- Adding a record and redirecting to the updated home view
- Updating record ID 1 and redirecting to the updated home view
- Deleting the highest-ID record and redirecting to the updated home view
- Visible loading, empty, and error states
- A responsive layout at 375px width

The API health endpoint is http://localhost:8498/health.

### Run the LangGraph workflow

All local-model calls inside the Planner and Reviewer nodes use
`src/model_client.py`.

```bash
python code/agents_graph.py \
  --title "Bus Delay at Santa Clara Station" \
  --content "The VTA Route 22 bus arrived thirty minutes late at Santa Clara Station and affected passengers during the afternoon commute." \
  --email "kazisaminamaraj.mumu@sjsu.edu" \
  --model qwen3:8b \
  --temperature 0.0 \
  --max-turns 10 \
  --strict
```

To demonstrate loop safety with forced Reviewer rejection:

```bash
python code/agents_graph.py \
  --title "Bus Delay at Santa Clara Station" \
  --content "The VTA Route 22 bus arrived thirty minutes late at Santa Clara Station and affected passengers during the afternoon commute." \
  --email "kazisaminamaraj.mumu@sjsu.edu" \
  --model qwen3:8b \
  --temperature 0.0 \
  --max-turns 2 \
  --strict \
  --force-review-issue
```

### Reproduce the HW2 experiments

The experiment runner saves each completed run immediately. Running the same
command again skips completed runs and resumes the selected phase.

```bash
caffeinate -i python code/run_hw2_experiments.py --phase schema
caffeinate -i python code/run_hw2_experiments.py --phase ceilings
caffeinate -i python code/run_hw2_experiments.py --phase adversarial
python code/run_hw2_experiments.py --phase summary
```

The experiment design is:

- 30 schema-validation runs using `reports/hw02/cases/schema_input.json`
- 20 runs with ceiling 2 and 20 runs with ceiling 10
- 5 runs using `reports/hw02/cases/adversarial_input.json`

Raw results are stored in `reports/hw02/raw/`. Calculated metrics are documented
in `reports/hw02/METRICS.md`, and timestamped execution progress is stored in
`reports/hw02/RUN_LOG.txt`.

### Verify HW2

Run from the repository root after creating the verification script:

```bash
python code/verify_hw02.py
```

The output is saved in `reports/hw02/verification.json`.

## Reports

See `reports/hw01/` and `reports/hw02/` for reports, run logs, raw experiment
data, metrics, AI-use disclosures, verification outputs, and screenshots.
