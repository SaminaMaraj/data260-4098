# AI Use Disclosure

## 1. What did I use an AI assistant for, and what did I do myself?

I used ChatGPT to help me understand the homework requirements, plan the file structure, write starting code, and troubleshoot errors. I personally created and organized the files in my repository, ran the FastAPI application, tested the CRUD operations, ran all 75 model experiments, reviewed the outputs, saved the evidence, and used Git to commit and push my work.

## 2. What was one unsuitable result?

The loading-state demonstration did not work at first. Even when I opened the loading-test URL, the page still displayed the incident records instead of the loading message.

## 3. How did I detect the problem?

I tested the page in the browser and then used `grep` to inspect the `loadIncidents` function. The output showed that the loading-test condition was missing from the saved JavaScript file.

## 4. What did I change, and why does it work now?

I added a condition that checks whether the URL contains `demo=loading`. When it does, the function displays the loading state and returns before requesting incident records. I saved the file and performed a hard refresh. The browser then displayed the loading message correctly.