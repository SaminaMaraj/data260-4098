# Reflection - HW5 Part 5

For this reflection I picked the max_steps scenario from agent_runs.jsonl (run 6170a6dc). In this run I asked the agent to look up INC-000002, then INC-000003, then INC-000004, then INC-000005 one at a time and summarize them at the end. The run used qwen3:8b through Ollama with max_steps set to 3.

At step 1, the harness sent my prompt and the three tool descriptions to the model. Instead of asking for one incident, the model asked for all four lookups at once. My harness only runs one tool call per step, so it ran get_incident for INC-000002 through execute_tool and recorded the other three as ignored_tool_calls. One of the ignored calls was even malformed: the INC-000005 request had a broken key ("5name") instead of a proper tool name. The INC-000002 result came back as ok: true in the {ok, data, error} envelope and was sent back to the model.

At step 2 and step 3 the model asked for INC-000003 and INC-000004, and both returned ok: true. In one of these steps it again asked for INC-000005 at the same time, and that extra call was also ignored. Nothing was blocked by the safety rule and there were no errors.

After step 3 the turn counter reached max_steps, so the harness stopped and logged stop_reason as max_steps. The model never got to look up INC-000005 or write its summary. So this run did not stop because the task was finished or because of the safety rule. It stopped because of the step ceiling.

This run showed me two things. The step limit stops a model that keeps asking for more work, and running only one tool call per step keeps the log easy to follow, even when the model sends several calls at once or a broken one.