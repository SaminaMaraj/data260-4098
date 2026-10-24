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
