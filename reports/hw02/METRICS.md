# HW2 Metrics

## Experiment configuration

- Model: qwen3:8b
- Temperature: 0.7
- Strict validation: enabled
- Fixed input: reports/hw02/cases/schema_input.json
- Adversarial input: reports/hw02/cases/adversarial_input.json
- Schema ceiling: 10 turns
- Adversarial ceiling: 2 turns

## Schema validation over 30 runs

| Outcome | Count | Mean latency (ms) |
|---|---:|---:|
| Valid first attempt | 30 | 40200.03 |
| Valid after one retry | 0 | N/A |
| Valid after two or more retries | 0 | N/A |
| Hit turn ceiling | 0 | N/A |

All 30 runs passed the Pydantic schema on the first attempt. Each result contained exactly three distinct tags. Every tag was between 3 and 30 characters, and every summary contained no more than 25 words.

## Turn-ceiling comparison

| Turn ceiling | Runs | Completed | Completion rate | Mean latency (ms) |
|---:|---:|---:|---:|---:|
| 2 | 20 | 20 | 100% | 38179.15 |
| 10 | 20 | 20 | 100% | 43585.15 |

I would use a ceiling of 2 for deployment. Both ceilings completed every run, but ceiling 2 was about 5.4 seconds faster on average and provides better protection against unnecessary or infinite correction loops.

## Adversarial-input results

| Runs | Hit ceiling | Hit-ceiling rate | Mean latency (ms) |
|---:|---:|---:|---:|
| 5 | 5 | 100% | 50638.00 |

The adversarial input told the model to violate the schema. During the first examined run, all three generated tags exceeded 30 characters and the summary exceeded 25 words. The validation errors were sent back to the Planner, but the second attempt still contained an oversized tag. The Supervisor therefore stopped the workflow at the two-turn ceiling.

One possible improvement is to identify instruction-like text inside user content and clearly isolate it as untrusted data. A separate deterministic repair step could also shorten invalid tags and summaries before validating them again.