# Card Benefit Activation Engine: Step 1.2

This folder contains the first RAG slice for the project. It converts real benefit-guide PDFs into searchable chunks while preserving issuer, card, benefit type, page, document title, and source URL.

## Run it

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python download_guides.py
python ingest.py
python retriever.py "What does purchase protection cover?" --issuer Chase --benefit-type purchase_protection
python llm_policy.py "What does purchase protection cover?" --issuer Chase --benefit-type purchase_protection
```

The PDFs are stored under `data/policy_pdfs/`, extracted chunks under `data/chunks.json`, and the retriever returns citations suitable for a later LLM prompt. The Citi source is marked as a third-party mirror and should be verified before production use.

## Pipeline

1. `sources.json` is the source registry.
2. `download_guides.py` downloads the registered documents.
3. `ingest.py` extracts text page by page and labels known benefit sections.
4. `retriever.py` performs a TF-IDF search and returns the most relevant clauses.

TF-IDF is an intentionally transparent baseline for the mid-evaluation. A later version can replace only the vectorizer with sentence embeddings and FAISS while keeping the chunk and citation contract unchanged.

## Structured LLM answers

`llm_policy.py` performs retrieval first, then sends only the retrieved policy evidence to Groq. It returns JSON containing the answer, limits, exclusions, required evidence, citations, and the retrieved chunk IDs. The script accepts the current raw-key `api.env` format or `GROQ_API_KEY=...` format. Keep `api.env` private and rotate any key that has been exposed.
