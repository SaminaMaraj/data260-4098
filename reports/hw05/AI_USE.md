# AI Use Disclosure - HW5

## 1. What did I use an AI assistant for, and what did I do myself?
I used ChatGPT to help write the starting code for each part: the Route table and migration, the Redux slice, the two MCP servers, the retry wrapper, execute_tool, the agent loop, and the verification script. I used Claude to help me plan the prompts, check ChatGPT's code before I ran it, understand error messages, and help draft my AI use and reflection write-ups. I ran everything myself on my Mac. I backed up the database before the migration, ran the migration and checked that all 5,000 incidents were kept, tested every endpoint in Postman, tested the MCP tools in MCP Inspector, ran the fault-injection experiment and the Ollama scenarios, took the screenshots, and committed and pushed my work with Git.

## 2. What was one unsuitable AI result?
The first version of the Part 4 test runner passed 7/7, but it was not testing my real tools. The test file defined its own fake_search_incidents, fake_get_incident and fake_incident_count_by_route functions and passed those to execute_tool. So the invalid-input tests were checking the fake functions' validation, not the validation in transit_server.py.

## 3. How did I detect the problem?
After the tests passed, I checked the imports in tests/run_tests.py with grep. It showed the fake tool functions and no import from transit_server. That meant the tests would still pass even if my real tools had a validation bug.

## 4. What did I change, and why does it work now?
I asked for the tests to call the real tool functions from transit_server.py and to replace only the database with an in-memory data source. Now the unknown category, the malformed incident code and the negative min_incidents cases are rejected by my real code. I confirmed the tests still pass (7/7, and 9/9 after Part 5) with the MySQL container stopped, so they run offline.