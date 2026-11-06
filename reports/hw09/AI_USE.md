# HW9 AI Use Disclosure - Kazi Samina Maraj Mumu

**1. What did I use an AI assistant for, and what did I do myself?**
I used Claude to help write the HW9 code (the Redis view counter, the semantic cache with the Redis vector index, the sweep and stale-answer scripts, the Answering and Evaluator agents and the lesson system), the datasets and cache_cases.yaml, a run guide, and to help write the report. I ran everything myself on my Mac with Redis Stack, my MySQL database s4098_rel and qwen3:8b, took all screenshots, checked the results and did the commits, tag and push.

**2. One AI-produced output that was wrong, and one thing I verified myself.**
The first stale-answer demo assumed VTA Route 522 had route code RT-003, based on the HW4 seed script. In my database RT-003 is VTA Route 22, so the demo changed the wrong route and the invalidation did not trigger. The reference fact for the Orange Line route code had the same wrong assumption. I checked the real route codes myself with a SQL query on s4098_rel (RT-001 Green Line, RT-002 Orange Line, RT-003 Route 22, RT-004 Route 522, RT-005 Route 55).

**3. How the problem was found.**
In the first run, step [2] showed 'VTA Route 22' even though the question was about Route 522, and the agent's own answer said Route 522 was RT-004.

**4. What was changed and why it works now.**
The demo now finds the route by name instead of by code. In the final run the data_version changed from 40ea672fa3da to 9929abc1046c, the old entry was deleted and the new answer said MV Transportation. I fixed the Orange Line fact to RT-002 before running Part 4, so no evaluation used the wrong value. cache_cases.yaml was not changed; the labeling mistake I found (C24) is documented in LABELING_NOTES.md.
