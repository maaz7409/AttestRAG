# Attest RAG

**Ask questions about your company's PDFs and get answers you can trust, with every claim cited to its source page and checked by an AI judge before you see it.**

Attest RAG is an end-to-end enterprise document Q&A platform. Upload policies, contracts, manuals or reports; ask questions in plain language; get a streamed answer with clickable citations. Behind the scenes, a **hybrid retrieval pipeline** (Qdrant dense vectors + BM25 keyword search) finds the right passages. A second model, the **LLM-as-a-Judge**, then grades every answer for **faithfulness, context relevance and toxicity** and withholds the ones that fail. Every question, source and score is logged to **PostgreSQL** and shown on an **analytics dashboard**.

![Chat with streamed answer, inline citations, judge verdict and sources](docs/screenshots/attest-rag-chat.png)

<sub>Screenshots were taken in the built-in offline mode (`LLM_PROVIDER=fake`). With OpenAI configured, answers are written by `gpt-4o-mini` and graded by the LLM judge.</sub>

---

## Why Attest RAG?

Plain chatbots over documents have three problems in a business setting:

| Problem | How Attest RAG handles it |
|---|---|
| **They miss things.** Vector search alone fails on exact terms like policy codes, clause numbers, product SKUs and names. | **Hybrid retrieval**: semantic search (OpenAI `text-embedding-3-small` in Qdrant) **plus** BM25 keyword search, merged with Reciprocal Rank Fusion. |
| **They make things up.** LLMs can state plausible facts that are nowhere in your documents. | **LLM-as-a-Judge** checks every answer against the retrieved passages and **blocks** hallucinated or toxic answers before delivery. |
| **You can't audit them.** Nobody knows what was asked, what was answered, or how good it was. | Every query is logged with **source attribution, latency breakdown and quality scores**, viewable on the dashboard and through the API. |

## Features

- 📄 **PDF ingestion**: drag-and-drop upload, page-aware chunking (every chunk maps to exactly one page), duplicate detection, and a clear message for scanned PDFs that have no text layer.
- 🔎 **Hybrid retrieval**: Qdrant dense search and BM25 run concurrently and are fused with weighted Reciprocal Rank Fusion. You can restrict search to selected documents.
- ⚡ **Real-time streaming**: answers stream token by token over Server-Sent Events.
- 🔗 **Interactive citations**: `[1]` markers become clickable chips that jump to the source card, showing file, page, the passage, and its dense, BM25 and fused scores.
- ⚖️ **LLM-as-a-Judge guardrails**: Pydantic-validated structured output with faithfulness, context relevance, answer relevance, toxicity, a list of unsupported claims, and the reasoning behind each score.
  - `stream` mode: tokens are shown immediately, the answer is judged right after, and it is retracted if it fails.
  - `strict` mode: the answer is buffered and released only after it passes, so nothing unverified ever reaches the user.
- 🗄️ **Audit trail in PostgreSQL**: questions, answers, status, a per-stage latency breakdown (retrieval, time to first token, generation, judge), the retrieved and cited chunks, and judge scores. Logs are written in the background, so they add no latency.
- 📊 **Analytics dashboard (Recharts)**: query volume, judge pass rate, p50/p95 latency, quality trends, score distributions, most-cited documents, and a searchable query trail with a full audit view for each query.
- 🐳 **One-command deployment** with Docker Compose, plus GitHub Actions CI/CD (tests, image builds to GHCR, SSH deploy).
- 🔌 **Offline mode**: `LLM_PROVIDER=fake` runs the entire product without an API key, using local embeddings, an extractive answerer and a heuristic judge. It's useful for demos, development and CI.

| Analytics dashboard | Document management |
|---|---|
| ![Analytics](docs/screenshots/attest-rag-analytics.png) | ![Documents](docs/screenshots/attest-rag-documents.png) |

## How it works

```
                ┌──────────────┐  upload PDF   ┌───────────────────────────────────────────┐
                │              │ ────────────▶ │ Ingestion: parse → page-aware chunks →     │
                │    React     │               │ embed → Qdrant (vectors) + PostgreSQL      │
                │  TypeScript  │               │ (text) + in-memory BM25 index              │
                │      UI      │               └───────────────────────────────────────────┘
                │              │  question     ┌───────────────────────────────────────────┐
                │  chat        │ ────────────▶ │ 1. Hybrid retrieval                        │
                │  citations   │               │    Qdrant dense ─┐                         │
                │  dashboard   │               │    BM25 keyword ─┴▶ Reciprocal Rank Fusion │
                │              │ ◀── SSE ───── │ 2. Generation (LangChain, streamed)        │
                │              │   sources,    │ 3. LLM-as-a-Judge (structured output)      │
                │              │   tokens,     │ 4. Guardrail: deliver / retract / withhold │
                │              │   verdict     │ 5. Async log → PostgreSQL                  │
                └──────────────┘               └───────────────────────────────────────────┘
                  nginx :3000                          FastAPI :8000
```

**Tech stack:** Python 3.12 · FastAPI · LangChain · OpenAI (`gpt-4o-mini`, `text-embedding-3-small`) · Qdrant · PostgreSQL 16 + SQLAlchemy 2 (async) · Pydantic v2 · React 19 · TypeScript · Vite · Recharts · Docker Compose · nginx · GitHub Actions

---

## Quick start (Docker, recommended)

You need [Docker](https://docs.docker.com/get-docker/) with the Compose plugin.

```bash
git clone https://github.com/maaz7409/attest-rag.git
cd attest-rag
cp .env.example .env
# edit .env and set OPENAI_API_KEY=sk-...
docker compose up --build
```

Then open:

| URL | What |
|---|---|
| http://localhost:3000 | Attest RAG web app |
| http://localhost:8000/docs | Interactive API documentation (Swagger) |
| http://localhost:6333/dashboard | Qdrant web UI |

**No OpenAI key?** Try the full product offline:

```bash
LLM_PROVIDER=fake docker compose up --build
```

### Using the app

1. Go to **Documents** and drop in one or more PDFs. Each one is parsed, chunked, embedded and indexed in a few seconds.
2. Go to **Ask** and type a question. Watch the answer stream in, click a citation chip to see the exact passage, and expand **Judge details** to see the scores and reasoning.
3. Optionally, use **All documents** to restrict the search to specific files.
4. Open **Analytics** to see volume, latency, quality trends and the full query trail. Click any row for its audit record.

---

## Local development (without Docker)

**Requirements:** Python 3.11+, Node.js 20+, and PostgreSQL and Qdrant running locally (or `docker compose up postgres qdrant`).

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload            # http://localhost:8000

# Frontend (second terminal)
cd frontend
npm install
npm run dev                              # http://localhost:5173 (proxies /api to :8000)
```

> Tip: `QDRANT_URL=:memory:` runs an embedded, in-process Qdrant, so you only need PostgreSQL to develop.

### Running the tests

```bash
cd backend && pytest -q                  # 37 tests: SQLite + in-memory Qdrant by default
TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/attestrag_test pytest -q

cd frontend && npm test                  # SSE parser, citation parser, chat state reducer
npm run typecheck && npm run build
```

---

## Configuration

All settings are environment variables (see [`.env.example`](.env.example)).

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `openai` | `openai` or `fake` (fully offline) |
| `OPENAI_API_KEY` | – | Required when `LLM_PROVIDER=openai` |
| `OPENAI_BASE_URL` | – | Optional: any OpenAI-compatible endpoint (Azure OpenAI, a gateway, …) |
| `CHAT_MODEL` / `JUDGE_MODEL` | `gpt-4o-mini` | Answer generator / evaluator models |
| `EMBEDDING_MODEL` / `EMBEDDING_DIM` | `text-embedding-3-small` / `1536` | Dense embedding model and vector size |
| `DATABASE_URL` | `postgresql+asyncpg://…localhost…` | PostgreSQL connection string |
| `QDRANT_URL` / `QDRANT_API_KEY` / `QDRANT_COLLECTION` | `http://localhost:6333` / – / `attestrag_chunks` | Vector store (`:memory:` for embedded mode) |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `1000` / `150` | Characters per chunk / overlap |
| `DENSE_TOP_K` / `SPARSE_TOP_K` | `20` / `20` | Candidates fetched from each retriever |
| `FINAL_TOP_K` | `6` | Passages handed to the LLM after fusion |
| `RRF_K`, `DENSE_WEIGHT`, `SPARSE_WEIGHT` | `60`, `1.0`, `1.0` | Reciprocal Rank Fusion tuning |
| `JUDGE_ENABLED` | `true` | Turn the evaluation layer on or off |
| `GUARDRAIL_MODE` | `stream` | `stream` (live tokens, retract on failure) or `strict` (release after passing) |
| `FAITHFULNESS_THRESHOLD` | `0.6` | Below this, the answer is **blocked** as a hallucination |
| `TOXICITY_THRESHOLD` | `0.5` | At or above this, the answer is **blocked** |
| `CONTEXT_RELEVANCE_THRESHOLD` | `0.4` | Below this, the answer is **flagged** (shown with a warning) |
| `MAX_UPLOAD_MB` | `25` | Maximum PDF size |
| `CORS_ORIGINS` | `http://localhost:5173,…` | Allowed browser origins when not served through nginx |

---

## API overview

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Liveness probe |
| `GET` | `/api/ready` | Readiness: PostgreSQL and Qdrant status, provider, guardrail mode, indexed chunks |
| `GET` | `/api/documents` | List documents |
| `POST` | `/api/documents` | Upload a PDF (`multipart/form-data`, field `file`) |
| `DELETE` | `/api/documents/{id}` | Delete a document and its vectors |
| `POST` | `/api/chat/stream` | Ask a question, streamed as Server-Sent Events |
| `POST` | `/api/chat` | Ask a question, returned as a single JSON response |
| `GET` | `/api/queries` | Paginated query trail (`?status=blocked`, …) |
| `GET` | `/api/queries/{id}` | Full audit record: answer, latency, sources, judge verdict |
| `GET` | `/api/analytics/overview?days=14` | Everything the dashboard shows |

Example:

```bash
curl -F "file=@employee-handbook.pdf" http://localhost:8000/api/documents

curl -N -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"question": "How many vacation days do employees get?"}'
```

The stream emits `start` → `sources` → `token`… → `evaluation` → (`blocked`) → `done`:

```
event: sources
data: {"type":"sources","sources":[{"index":1,"filename":"employee-handbook.pdf","page_number":4,...}]}

event: token
data: {"type":"token","content":"Employees receive 25 days"}

event: evaluation
data: {"type":"evaluation","faithfulness":0.95,"context_relevance":0.9,"toxicity":0.0,"passed":true,...}

event: done
data: {"type":"done","status":"answered","cited":[1],"latency":{"total_ms":1840.2,...}}
```

---

## Project structure

```
attest-rag/
├── backend/                  FastAPI service
│   ├── app/
│   │   ├── api/routes/       HTTP endpoints (documents, chat, queries, analytics, health)
│   │   ├── core/             Settings and logging
│   │   ├── db/               SQLAlchemy models and async engine
│   │   ├── schemas/          Pydantic API models and the JudgeVerdict schema
│   │   └── services/         ingestion, bm25, vector_store, retrieval, generation,
│   │                         judge, pipeline, analytics, providers, container
│   ├── tests/                pytest suite
│   └── Dockerfile
├── frontend/                 React + TypeScript (Vite)
│   ├── src/api/              Typed API client and SSE streaming
│   ├── src/components/       Citations, sources, judge panel, charts, drawer
│   ├── src/pages/            Ask, Documents, Analytics
│   ├── nginx.conf            Static hosting and /api reverse proxy (SSE-aware)
│   └── Dockerfile
├── .github/workflows/        CI and CD pipelines (see below)
├── docker-compose.yml        PostgreSQL + Qdrant + backend + frontend
└── .env.example
```

## CI/CD

- **CI** (`ci.yml`) runs on every push and pull request: ruff lint and format check, pytest against a real PostgreSQL service, frontend typecheck, tests and build, then a full `docker compose` build with an end-to-end smoke test through nginx.
- **CD** (`cd.yml`) runs on pushes to `main`: it builds and pushes `backend` and `frontend` images to GitHub Container Registry, tagged `sha-<commit>` and `latest`. If you set the repository variable `DEPLOY_ENABLED=true` and the secrets `DEPLOY_HOST`, `DEPLOY_USER` and `DEPLOY_SSH_KEY`, it also deploys over SSH to any Docker host (an AWS EC2, GCP or Azure VM, a DigitalOcean droplet, …) with `docker compose pull && docker compose up -d`.

## Limitations and roadmap

- Scanned, image-only PDFs need OCR first (they are rejected with a clear message).
- The BM25 index lives in process memory (it is rebuilt from PostgreSQL at start-up). For multi-replica deployments, move keyword search to Qdrant sparse vectors or OpenSearch.
- The schema is created automatically at start-up. Add Alembic migrations before evolving it in production.
- There is no authentication yet. Put Attest RAG behind your SSO or reverse proxy, or add OAuth2 to FastAPI.
- Possible next steps: cross-encoder re-ranking, query rewriting for follow-up questions, DOCX/HTML ingestion, and per-tenant document permissions.
