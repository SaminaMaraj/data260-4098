# RAG Analysis

For the RAG experiment, I used five documents related to municipal transit
safety and security incidents. The documents included public transit
safety/security information and three smaller documents about incident records,
incident response, and data quality.

I divided the documents into overlapping 500-character chunks, with 50
characters of overlap between chunks. I then created embeddings using
`all-MiniLM-L6-v2` and stored them in a FAISS vector index. The answers were
generated using the local Ollama model `qwen3:8b`.

I compared three approaches. No RAG answered the questions without using any
retrieved documents. Basic RAG gave the retrieved text to the model as
context. Context-engineered RAG added source labels, asked the model to cite
the sources, and instructed it to refuse questions that were not supported by
the documents.

The experiment included six questions. Questions Q1 through Q4 were related
to the transit documents. Q5 asked for the fare of VTA Route 55, and Q6 asked
who won the 2025 World Series. These last two questions were intentionally
outside the document collection and were used to test whether the model would
refuse unsupported questions. In total, the experiment produced 18 comparison
records: six questions tested with each of the three configurations. I also
ran a top-k sweep using k values of 1, 3, and 5.

The No RAG and Basic RAG approaches often produced reasonable-looking
answers, but their answers were not always supported by the provided
documents. Context-engineered RAG performed better for unsupported questions.
It correctly refused the fare question and the World Series question instead
of confidently inventing an answer. It also produced grounded answers for
some of the supported transit questions, including the meaning of a major
transit event.

One limitation was the retrieval quality. Even after increasing the main
retrieval size to 15 chunks, the system sometimes ranked the larger HTML and
CSV documents above the smaller custom text documents. Because of this, the
automatic `correct_retrieval` metric remained false for several supported
questions. This was not a programming failure; it showed that vector
similarity alone was not always enough to find the best domain-specific
document. A stronger production system could combine vector search with
keyword matching, metadata filters, or a reranking step.

Overall, Context RAG was the safest approach because it used document context,
identified sources, and refused questions that were not supported. The
experiment showed that retrieval quality and answer quality should be
evaluated separately, and that grounding is important for reducing unsupported
or hallucinated answers.