# TenderBot (MVP)

**Pitch:** TenderBot (MVP) helps CZ/SK companies quickly find relevant public tenders (TED/NEN), compare conditions, and get alerts. This repo is a demo showing an end‑to‑end RAG pipeline: Ingest → Validate → Embed → Vector DB → API → UI → Alerts.

## Quickstart (local Docker)
```bash
cp .env.example .env
docker compose up --build
```
- API: http://localhost:8000/docs
- UI: http://localhost:8501
- Qdrant: http://localhost:6333 (console)

Seed sample data (in another terminal):
```bash
docker compose exec api python -m scripts.seed_sample
```

## Minimal API usage
```bash
curl localhost:8000/health
curl -X POST localhost:8000/ingest
curl -s "localhost:8000/search?q=software" | jq
curl -s -X POST localhost:8000/qa -H 'Content-Type: application/json' -d '{"question":"What is the deadline?"}' | jq
```

## Architecture (high level)
```mermaid
flowchart LR
  A[CSV/HTML/PDF notices] --> B[Prefect Ingest]
  B --> C[Validation (Great Expectations)]
  C --> D[Embeddings]
  D --> E[Qdrant]
  E --> F[FastAPI]
  F --> G[Streamlit UI]
  F --> H[Alerts (cron/Prefect)]
```

## Tech choices
- **Qdrant** for vector search (local container). 
- **Embeddings** via Sentence-Transformers (default MiniLM for lightweight demo, switchable to E5 via env var).
- **FastAPI** for clean, typed HTTP API (+ OpenAPI docs).
- **Streamlit** for a fast demo UI.
- **Great Expectations** for simple data checks.
- **Prefect** for orchestrating ingest and future alerts.

## Costs & perf (demo)
- Local CPU-only; small model keeps it fast. For prod, swap to E5 and add reranker.

## CI/CD
- `ci.yml` runs lint + tests on PRs.
- `api.yml` and `ui.yml` show example build+push to GHCR/ACR (set secrets), then deploy to Azure Container Apps.

## License
MIT (adapt as needed).
