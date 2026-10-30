# AI_USE.md

This file records how each partner used AI assistants while building
Lab 1, with incorrect outputs, how they were detected, and how they
were fixed.

Two kinds of AI were involved:

- **Coding assistants** (ChatGPT and Claude) used during development
  for planning, code drafts, debugging, rubric review, and documentation
  review.
- **The runtime model** (qwen3:8b through Ollama) that powers the
  application's assistant.

All code was reviewed, run, and tested locally before it was committed.

---

## Kazi Samina Maraj Mumu

### How I used AI assistants

- ChatGPT: writing prompts for each weekly task, drafting FastAPI routes,
  SQLAlchemy models, the seed generator, and assistant tools, and
  debugging errors.
- Claude: reviewing the repository against the Lab 1 rubric, finding
  problems in the assistant loop, and writing fixes for the follow-up
  validation, repair path, and confirmation flow.
- Both: reviewing METRICS.md, RUN_LOG.txt, and this file.

### Incorrect output 1 (coding assistant): test-specific overrides in the loop

**What was wrong.** An early version of `loop.py` generated with a
coding assistant checked the user's message for exact phrases such as
"remote data science internship" and "computer science students next
month", then replaced the model's tool arguments with fixed values.
It also copied saved preferences over every `search_jobs` call. The
required tests passed, but because the code chose the arguments, not
the model. The preference overwrite also undid the model's
"higher-paying" change in the follow-up test.

**How it was detected.** A rubric review of the repository read the
loop line by line and found the phrase checks. Comparing the tool-call
log with the code showed the arguments came from the overrides.

**Fix.** The phrase checks and the preference overwrite were removed.
The real causes were fixed instead:

- Today's date is in the system prompt, so the model can compute
  "next month".
- `category` is an `enum` of the four valid values in the tool schema.
- Invalid arguments are rejected with a specific error and one retry
  (the repair path).

Only the student ID is still set by the code, for security.

### Incorrect output 2 (runtime model): company numbers used as job IDs

**What was wrong.** In the follow-up test ("From those results, show me
the higher-paying options"), qwen3:8b called `rank_jobs` with
`[18, 31, 49, 9, 45, 26, 19, 41, 40, 21]`. These were the numbers from
company names such as "Pair 15 Company 0018", not job IDs. The real IDs
from the previous search were different.

Before validation was added, the model had also sent made-up IDs such
as `[123, 456, 789]`. Because the database has 300 jobs, an ID like 123
is a real job that was not in the search, so it could have ranked the
wrong jobs silently.

**How it was detected.** The new validation compared the requested IDs
with the IDs from the most recent `search_jobs` result and rejected
them. The run stopped with `repair_failed` and failures
`['text_instead_of_tool', 'malformed_arguments']`.

**Fix.**

- `search_jobs` now starts its result with a `JOB_IDS: [...]` line,
  and each job's field is named `job_id`.
- The repair error says only the `job_id` values on the `JOB_IDS` line
  are valid, that numbers in company names are not job IDs, and lists
  the valid IDs.
- The text-only repair and the tool-call repair have separate one-time
  limits, so a text reply cannot use up the repair the ID error needs.

### Incorrect output 3 (coding assistant): confirmation the model could approve

**What was wrong.** The first `confirm_action` returned True when the
argument `confirmed` was True. The model filled in that argument, so the
model could approve its own save and the student was never asked.

A later coding-assistant version used `input()`. That worked in a
terminal test, but inside FastAPI it would make the server wait for
typing in its own terminal, so a save from the website would hang.

**How it was detected.** Code review against the rubric requirement
"If the student declines, return a cancellation string to the model".

**Fix.** `confirm_action` now returns `approved`, `declined`, or
`pending`. On the API it never calls `input()`: the loop stops with
`pending_confirmation`, the server stores the pending action, and the
student answers through `POST /assistant/confirm`. `confirmed` was
removed from the tool schema, and `auto_approve` is stripped from
anything the model sends.

### Incorrect output 4 (runtime model): wrong student ID

**What was wrong.** In the first assistant test, the model called
`get_student_preferences {"student_id": 123}` when the request was for
student 1.

**How it was detected.** The tool-call log was compared with the
`student_id` passed to `run_assistant()`.

**Fix.** The loop always sets `student_id` from the application, and
`student_id` was removed from the tool schemas so the model no longer
asks the student for it.

---

## Bhavana

TODO (Bhavana): describe your own AI assistant use for the frontend and
integration work, with one incorrect output, how you detected it, and
how you fixed it. Each partner must have their own entry.
