# HW3 Retrieval Metrics

## Experimental setup

- Corpus: `254,170` bytes across two public FTA transit safety/security sources.
- Embedding model: `sentence-transformers/all-MiniLM-L6-v2`.
- Vector index: in-memory LlamaIndex index for each chunking method.
- Questions: 5 fixed questions from `questions.yaml`.
- Retrieval depth: top-5 (`k=5`).
- Vector dimension: 384.

## Chunking comparison

| Technique | Chunks | Average chunk length | Mean top-1 cosine | Mean cosine@5 | Recall@5 | Mean latency (ms) |
|---|---:|---:|---:|---:|---:|---:|
| Token | 334 | 653.34 | 0.6083 | 0.4983 | 5/5 | 32.40 |
| Semantic | 32 | 5,727.38 | 0.5151 | 0.3471 | 5/5 | 21.85 |
| Sentence-window | 579 | 316.54 | 0.5622 | 0.4492 | 4/5 | 28.73 |

## Interpretation

Token chunking produced the strongest average retrieval quality in this run and retrieved the expected source for all five questions. Semantic chunking was fastest on average and produced far fewer, much larger chunks, but its cosine scores were lower. Sentence-window chunking produced the most chunks and performed well for the FTA overview questions, but missed the expected answer keyword for one question at `k=5`.

The experiment recorded 15 question/technique summaries and 75 individual retrieved rows. Three top-ranked rows were flagged as potentially misleading because the highest-scoring row did not contain an expected answer keyword. This shows that a high similarity score is not by itself proof that a retrieved passage answers the question.

## Reproducibility

The raw measurements are in `raw/retrieval_summaries.json` and `raw/retrieval_outputs.jsonl`. The flagged cases are in `raw/misleading_candidates.json`. The corpus files and their SHA-256 hashes are recorded in `CORPUS_MANIFEST.json`.
