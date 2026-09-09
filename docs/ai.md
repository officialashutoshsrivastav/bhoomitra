# Search, retrieval and the AI assistant

## Hybrid search

A query runs against two backends and the ranked lists are merged with **reciprocal rank fusion**
(`score = Σ 1/(k + rank)`, k = 60):

* **Keyword** — OpenSearch when `OPENSEARCH_URL` is set, otherwise PostgreSQL `tsvector` full-text
  search with `ts_rank` and `pg_trgm` for autocomplete.
* **Semantic** — cosine similarity over `document_chunks.embedding` in pgvector.

Each hit reports `matched_by: ["keyword","semantic"]`, its component scores and the fused score, so
relevance is explainable. Filters (type, topic, geography, year, language, source, organisation) and
entity types (document, dataset, policy, layer, challenge, place) apply to both backends.

## Embeddings

| Provider | When | Notes |
| --- | --- | --- |
| `hashing` (default) | No API key needed | Deterministic feature-hashed uni/bi-gram vectors, L2-normalised, reproducible, useful lexical-semantic similarity |
| `openai` | `EMBEDDING_PROVIDER=openai` + `OPENAI_API_KEY` | `text-embedding-3-small` (1536 dims) |

Changing provider requires a re-index (Administration → Jobs → *Rebuild search index*).

## RAG pipeline

```
question → query analysis → hybrid retrieval (top-k chunks, k = RAG_TOP_K)
        → re-rank → evidence sufficiency check
        → generation constrained to the retrieved passages
        → answer + numbered citations + confidence + recommendation record
```

* **Refusal is a feature.** If no passage supports the question the assistant returns
  `evidence_sufficient: false`, confidence 0.0 and says it cannot answer. It never invents sources.
* **Citations** carry document id, title, locator (page/section), the exact excerpt, whether the
  marker was actually used in the answer, and `is_demo`.
* **Two generators:**
  * `local-extractive` (default) — selects and quotes the supporting sentences with `[n]` markers.
    No API key, no hallucination surface.
  * `openai` — an LLM prompted to answer *only* from the numbered passages and to cite each claim;
    markers not present in the passage set are stripped before the answer is returned.
* Each answer is persisted as a `Recommendation` with ranked `Evidence` rows and provenance edges,
  and appears in the conversation history.

## Evidence engine and value kinds

`GET /evidence/{id}` returns the statement, confidence basis, limitations, ranked evidence,
assumptions and a step-by-step explanation of how the output was produced.
`GET /evidence/{id}/trace` returns a graph the UI renders as layered boxes.

| Label | Meaning |
| --- | --- |
| **OBSERVED** | Measured or reported value taken from a source dataset or document |
| **MODELLED** | Computed by a model or statistical procedure |
| **ASSUMPTION** | A declared input the user or system supplied |
| **SCENARIO** | A “what if” input defining an intervention |
| **UNCERTAINTY** | A range (p10–p90 band, confidence interval) rather than a point value |

Every projection carries the disclaimer: *decision-support output, not an official government
decision or statistic*.
