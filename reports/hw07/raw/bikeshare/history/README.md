# Historical Part 4 runs (kept unchanged as evidence)

These are the first saved UI runs from 2026-10-23 (before the deterministic
validator existed). The files are exactly as the run wrote them.

| Run | Agent pay-per-use | Correct pay-per-use | What went wrong |
|---|---|---|---|
| scenario_A_unlock_omitted | $4,260.05 | $4,860.05 | the agent's SQL dropped the `UNLOCK +` term (600 rides x $1.00); `membership_fees` was reported as $1,771.88, which is the membership total, not the $435 in passes; break-even 5.95 instead of 4.94 |
| scenario_B_unlock_omitted | $676.97 | $1,196.97 | the agent's SQL dropped the `UNLOCK +` term (520 rides x $1.00); break-even 22.28 instead of 12.6 |

The decisions in both runs were still correct, but the totals, weekly spend and
break-even values were wrong. The final runs are in `../scenario_A/` and
`../scenario_B/`; each has a `validation` section with every check.

## Revised agent, first scenario A run (2026-10-23, kept unchanged)

`scenario_A_decision_feedback_bug/`: the first run with the validator. All numbers
were correct ($600 unlock fees, $4,860.05 pay-per-use, $435 passes, $1,771.88
membership, break-even 4.94) and the justification said membership is cheaper,
but the decision field was "Pay Per Ride/Minute". Validation failed on the two
decision checks, the one correction round ran, and the answer stayed wrong, so
the run correctly ended with `validation_failed`. The cause was partly my
feedback message: for a decision-only failure it still said "recompute the
failed values with csv_sql and calculator", so the agent recomputed correct
numbers instead of fixing the decision. The message now says the numbers passed
and points to step 6 with the agent's own two totals.

## Runs on 2026-10-23 evening (all kept or described here)

- `scenario_A_old_server_run2/`: second scenario A run. The server was still
  running the code from before the decision-feedback fix, so the feedback was
  the old message; the decision stayed wrong (`validation_failed`).
- Third scenario A run (with the decision-feedback fix): round 0 failed only the
  two decision checks, the feedback showed the agent its own totals, round 1
  passed all 16 checks (`final_answer`, 9 tool calls, 92.7 s). Its run.json was
  then overwritten by mistake, because I ran scenario B with the label still
  set to `scenario_A`. Only its screenshots and its RUN_LOG.txt lines remain.
- `scenario_B_breakeven_hint_missing/`: that scenario B run (its file says
  label "scenario_A", but the CSV is scenario_B_payg.csv, 520 rows). All totals
  were correct ($1,196.97 vs $7,540.00, Pay Per Ride/Minute) but the agent
  reported the break-even as 2.0 (it used rides / rider_months) instead of 12.6.
  The feedback had no hint for this field, the agent recomputed other values
  and kept 2.0, so the run ended `validation_failed`. Every failed check now
  repeats its formula from the prompt (never the reference value).
