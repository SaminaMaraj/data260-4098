# HW7 AI Use Disclosure - Kazi Samina Maraj Mumu

> DRAFT - edit so every sentence matches what you actually did.

**1. What did I use an AI assistant for, and what did I do myself?**
I used Claude to read my HW5/HW6 reports and repository and to draft the HW7 code:
the JWT/role module and MySQL migration, the hand-written agent loop with its repair
path, the deterministic verifiers and Reflexion loop, the Bay Wheels tools, LangGraph
agent and UI, the hostile fixtures and attack runner, the file tools and safety gate,
offline tests and `verify_hw07.py`. I ran everything myself on my Mac: the migration
on my MySQL container, the Postman requests, the pre-commit demonstration, all
qwen3:8b runs, downloading the Bay Wheels trip data, the attack matrix, and
`make verify-hw07`. I took the screenshots, checked the numbers in the report against
`raw/`, and committed, tagged and pushed the work.

**2. One AI-produced output that was wrong or unsuitable.**
The first version of `is_destructive()` only recognised recursive deletion as the
literal text `rm -rf`. Because `find` is in `SAFE_PREFIXES`, the command
`find . -name '*.pyc' -delete` was **allowed**, which is a false allow on a recursive
delete. `rm -fr` and `rm -r -f` were also not recognised as destructive.

**3. How the problem was detected.**
The 10-command safety-gate test compares every command with its expected result. The
row for `find . -name '*.pyc' -delete` expected *block* but got *allow*. The test run
still prints the v1 result next to the final result so the false allow stays visible.

**4. What changed, and why it works now.**
The deny-list now treats `rm` with an `r`/`R` flag in any position or `--recursive`,
`find … -delete`, `find … -exec rm`, `xargs rm` and Python `shutil.rmtree` as recursive
deletion. The deny-list is checked *before* `SAFE_PREFIXES`, so a safe prefix can never
override it. The final run blocks all 5 destructive commands and allows all 5 safe ones.
