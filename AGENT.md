# Code Review and Transit Incident Memory Agent Instructions

- Review submitted code for correctness, security, performance, and readability.
- Respond using bullet points only when acting as the code-review agent.
- Begin every review response line with `- `.
- Keep review bullets concise and specific, with no more than five bullets.

- Project description: this repository implements a municipal transit incident API and memory assistant.
- Technology stack: keep the existing FastAPI, SQLAlchemy/MySQL, MongoDB, React, and Ollama components compatible.
- Coding convention: use clear snake_case Python names, typed function signatures, small modules, and helpful error messages.
- Testing approach: add an objective smoke test for every new endpoint and run offline validation tests when a live database or model is unnecessary.
- Testing approach: preserve reproducibility by using SID4=4098 and VERIFY_SEED=264098 for generated experiments.
- Prohibited action: never commit passwords, API keys, session secrets, virtual environments, or generated cache directories.
- Prohibited action: do not delete or rewrite existing HW1-HW5 behavior when adding HW6 features.
- Memory rule: treat user-specific memory as scoped to the user_id and never mix records between users.
