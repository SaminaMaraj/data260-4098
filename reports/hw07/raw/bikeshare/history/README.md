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
