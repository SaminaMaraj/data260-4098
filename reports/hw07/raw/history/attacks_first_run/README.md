# First Part 5 attack run (2026-10-23, kept unchanged as evidence)

Produced by the first version of `code/run_hw07_attacks.py`. It saved the SQL
log and the final answer of each cell, but not the full tool timeline, and the
exfiltration judge only counted ride_ids. The revised runner (results in
`../../attacks.json` and `../../attacks/*/trace.json`) saves the complete trace
of every cell, checks station names and timestamps too, and adds a control
run on the real pricing page.

Outcome of this first run: the model never sent a non-SELECT statement and
never copied raw rows into an answer; the only "success" was a wrong
membership decision before defenses that repeated no injected text.
