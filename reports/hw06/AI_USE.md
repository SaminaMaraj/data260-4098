# AI_USE

1. I used an AI assistant to help plan the HW6 structure, draft MongoDB schemas and routes, and explain error messages. I ran, tested, and verified the code myself.
2. One result I independently checked was the memory embedding implementation. Python's built-in `hash()` is not stable between processes, so it was unsuitable for reproducible experiments.
3. I detected the issue by reviewing the experiment requirements and checking whether the same fact would produce the same vector in a new Python process.
4. I changed the embedding index to use SHA-256, which produces deterministic vectors and makes the retrieval experiment reproducible.
