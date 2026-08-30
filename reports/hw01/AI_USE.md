# AI Use Disclosure

## 1. What I used an AI assistant for and what I did myself

I used ChatGPT to help interpret the assignment requirements, explain unfamiliar
Docker and AWS steps, suggest code structures, troubleshoot errors, and verify
the experiment calculations. I personally created and organized the project,
typed and ran the commands and code, selected the transit-incident input,
configured Docker and AWS, conducted the 40 local model runs, inspected the
outputs, and captured the screenshots.

## 2. One unsuitable result or independently verified item

The original starter used an outdated
`langchain_community.chat_models.ChatOllama` import. My active Anaconda
environment also used Python 3.13 even though the assignment required Python
3.11 or 3.12. This caused an import failure and was unsuitable for the required
environment.

## 3. How I detected or verified the problem

I detected the import problem from the terminal traceback. I then checked the
assignment PDF, confirmed its Python version requirement, checked my active
version with `python --version`, and verified the current Ollama integration
against the official LangChain and Ollama documentation.

## 4. What I changed and why it works now

I created a Python 3.12 virtual environment, installed the current Ollama
packages there, and replaced the removed integration with a reusable adapter in
`src/model_client.py`. The final agent pipeline and command-line client both
completed successfully, token counts were recorded, all five code-review
responses followed the required bullet-only format, and the raw experiment data
contains all 40 required runs.