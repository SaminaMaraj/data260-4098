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
- Fourth scenario A run: round 0 failed only the decision checks, round 1
  passed 16/16 (`final_answer`, 9 tool calls, 92.6 s). Its run.json was again
  overwritten by a scenario B run started with the label still "scenario_A"
  (the page always pre-filled that label). Screenshots and RUN_LOG.txt lines
  remain. The UI now sets the label from the CSV name, and the API moves an
  existing run to `history/<label>_replaced_<time>/` instead of overwriting it.
- `scenario_B_run2_breakeven/`: second scenario B run, with the formula hint.
  Same mistake: the agent computed `520 / 260` and reported 2.0 as the
  break-even in both rounds, so `validation_failed`. Because this is now a
  repeatable model error on a derived ratio, the harness has one last, logged
  step (see `DERIVED_FORMULAS` in src/hw7_bikeshare_agent.py).

## Harness-corrected run, replaced (2026-10-23 evening)

- `scenario_B_harness_corrected/`: the scenario B run shown as "final" in my
  first revised report. Totals and decision were right, but qwen3:8b reported
  the break-even as 1100.73 in rounds 0 and 1 (it used `260 * 29 / 520 / 6.85
  * 520`), so a harness step overwrote it with 12.6 and labelled the run
  `passed_after_harness_correction`. The written justification still said
  1100.73. This is not acceptable as a final result, so the harness step was
  removed. Now the feedback for a wrong derived ratio gives the calculator
  expression filled with the agent's OWN validated values (never the result),
  the agent must make that calculator call itself, up to two feedback rounds
  are allowed, and a new check fails any justification that still states an
  old number.

## First run with 17 checks: false rejection by my justification check (2026-10-24)

- `scenario_B_justification_check_bug/`: the agent's numbers, decision and
  justification were all correct ("pay-per-use cost for 520 rides is
  $1196.97 ... break-even ... 12.598"), but my new justification check read
  "520" (a ride count) as the pay-per-use total and failed the run
  (`validation_failed`). This was a verifier false rejection caused by my
  code. Fix: money labels are only compared with dollar amounts, the window
  stops at the end of the sentence, and a label passes if any number in it
  matches. Regression test: `test_consistent_justification_with_counts_is_not_flagged`.

## Replaced 16-check scenario A run (2026-10-23 evening)

- `scenario_A_before_17_checks/`: the scenario A run shown as final in my first
  revised report. Round 0 failed only the two decision checks, round 1 passed
  16/16. It was replaced because the validator now has 17 checks (the new
  "justification uses the final numbers" check) and the final runs had to use
  the same code.

## Final runs (2026-10-24, commit 7ea9737) in `../scenario_A/` and `../scenario_B/`

- Scenario B: round 0 failed only the break-even (3275.604234, from
  `7540.0 / (1196.97 / 520)`). The feedback gave the step 5 formula and the
  calculator expression with the agent's own validated values; the agent then
  called `29 / ((1196.97 - 0) / 520)` itself (12.598478) and round 1 passed
  17/17. No value was changed by the harness.
- Scenario A: 17/17 in round 0, no feedback.
