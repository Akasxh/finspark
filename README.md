# FinSpark

AI-assisted integration configuration and orchestration engine for fintech systems.

## What It Does

- **Document ingestion** -- upload PDF, DOCX, YAML specs and auto-extract API endpoints, field mappings, and schemas
- **Configuration generation** -- LLM-powered config generation with lifecycle management (draft -> review -> approved -> deployed), versioning, rollback, and diff
- **Simulation engine** -- dry-run configurations step-by-step against adapter rules before deploying to production
- **Audit and governance** -- full audit trail, webhook notifications, and search across all resources

## Tech Stack

| Layer | Tools |
|-------|-------|
| Backend | Python 3.11+, FastAPI, SQLAlchemy (async), Pydantic v2, Alembic |
| Frontend | React 18, TypeScript, Tailwind CSS v4, TanStack Query, Recharts |
| AI | Google Gemini (gemini-3-flash-preview), sentence-transformers |
| Database | SQLite (dev) / PostgreSQL (prod) via async drivers |
| Testing | pytest + pytest-asyncio (backend), Vitest + Testing Library (frontend) |
| Linting | Ruff (backend), Biome (frontend) |

## Quick Start

**Prerequisites:** Python 3.11+, Node.js 18+, [uv](https://docs.astral.sh/uv/)

```bash
# 1. Clone and set up environment
git clone https://github.com/Akasxh/finspark.git && cd finspark
cp .env.example .env
# Edit .env -- set FINSPARK_SECRET_KEY and optionally FINSPARK_GEMINI_API_KEY

# 2. Install and run the backend
uv sync
uv run alembic upgrade head
uv run uvicorn finspark.api.main:app --reload --port 8000

# 3. Install and run the frontend (new terminal)
cd frontend && npm install && npm run dev
```

Open `http://localhost:5173` for the UI, `http://localhost:8000/docs` for Swagger.

## Project Structure

```
finspark/
├── src/finspark/              # Backend source
│   ├── api/
│   │   ├── main.py            # FastAPI app entry point
│   │   └── routes/            # Route handlers (10 modules)
│   ├── core/                  # Config, database, security
│   ├── models/                # SQLAlchemy models
│   ├── schemas/               # Pydantic request/response schemas
│   └── services/              # Business logic, LLM client
├── frontend/src/
│   ├── pages/                 # 8 page components
│   ├── components/            # Shared UI (Layout, Pagination)
│   ├── hooks/                 # React Query hooks
│   ├── lib/                   # API client, utilities
│   └── types/                 # TypeScript type definitions
├── alembic/                   # Database migrations
├── tests/                     # Backend test suite
└── docker-compose.yml         # Container orchestration
```

## API Overview

All endpoints prefixed with `/api/v1`. Responses use a standard `APIResponse` wrapper.

| Resource | Method | Endpoint | Description |
|----------|--------|----------|-------------|
| **Health** | `GET` | `/health` | Service health check |
| **Documents** | `POST` | `/documents/upload` | Upload PDF/DOCX/YAML |
| | `GET` | `/documents/` | List all documents |
| | `GET` | `/documents/{id}` | Document detail with extracted data |
| | `DELETE` | `/documents/{id}` | Delete a document |
| **Configurations** | `POST` | `/configurations/generate` | LLM-generate config from adapter + document |
| | `GET` | `/configurations/` | List configurations |
| | `GET` | `/configurations/{id}` | Config detail |
| | `PATCH` | `/configurations/{id}` | Update config fields |
| | `POST` | `/configurations/{id}/validate` | Validate against schema rules |
| | `POST` | `/configurations/{id}/transition` | Lifecycle state transition |
| | `GET` | `/configurations/{id}/history` | Version history |
| | `POST` | `/configurations/{id}/rollback` | Rollback to previous version |
| | `GET` | `/configurations/{id}/export` | Export as JSON/YAML |
| | `GET` | `/configurations/{a}/diff/{b}` | Diff two configurations |
| | `GET` | `/configurations/templates` | List config templates |
| | `GET` | `/configurations/summary` | Aggregate stats |
| | `POST` | `/configurations/batch-validate` | Validate multiple configs |
| | `POST` | `/configurations/batch-simulate` | Simulate multiple configs |
| **Adapters** | `GET` | `/adapters/` | List integration adapters |
| | `GET` | `/adapters/{id}` | Adapter detail |
| | `GET` | `/adapters/{id}/match` | Match adapter to document fields |
| **Simulations** | `POST` | `/simulations/run` | Run simulation against config |
| | `GET` | `/simulations/` | List simulations |
| | `GET` | `/simulations/{id}` | Simulation detail with steps |
| | `GET` | `/simulations/{id}/stream` | SSE stream of simulation progress |
| **Webhooks** | `POST` | `/webhooks/` | Register webhook |
| | `GET` | `/webhooks/` | List webhooks |
| | `DELETE` | `/webhooks/{id}` | Remove webhook |
| | `POST` | `/webhooks/{id}/test` | Send test delivery |
| **Search** | `GET` | `/search/` | Full-text search across resources |
| **Audit** | `GET` | `/audit/` | Paginated audit log with filters |
| **Analytics** | `GET` | `/analytics/dashboard` | Dashboard metrics |
| | `GET` | `/analytics/health` | System health metrics |
| | `GET` | `/metrics` | Prometheus-style metrics |

## Screenshots

The frontend uses a Deep Slate + Steel Blue fintech design system with IBM Plex Sans/Mono typography. Navigation groups pages into Core (Dashboard, Documents, Search), Integrations (Adapters, Configurations, Simulations), and Governance (Webhooks, Audit Log).

See `docs/screenshots/` for UI captures.

## Testing

```bash
# Backend (850+ tests, ~82% coverage)
uv run pytest
uv run pytest --cov-report=html    # HTML coverage report

# Frontend
cd frontend
npm run test:run                    # Run once
npm run test:coverage               # With coverage

# Linting
uv run ruff check src/              # Backend
cd frontend && npm run lint         # Frontend
```

## Environment Variables

Copy `.env.example` to `.env` and configure:

| Variable | Description | Default |
|----------|-------------|---------|
| `FINSPARK_DATABASE_URL` | Async database URI | `sqlite+aiosqlite:///./finspark.db` |
| `FINSPARK_SECRET_KEY` | App secret for signing | (required) |
| `FINSPARK_ENCRYPTION_KEY` | Encryption key for sensitive data | (required) |
| `FINSPARK_DEBUG` | Enable debug mode | `false` |
| `FINSPARK_AI_ENABLED` | Enable LLM features | `false` |
| `FINSPARK_GEMINI_API_KEY` | Google Gemini API key | -- |
| `FINSPARK_GEMINI_MODEL` | Gemini model identifier | `gemini-3-flash-preview` |
| `FINSPARK_OPENAI_API_KEY` | OpenAI API key (fallback) | -- |

## License

MIT
