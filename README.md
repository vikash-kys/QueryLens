# QueryLens

QueryLens is a PostgreSQL analytics workbench with natural-language-to-SQL generation, a read-only SQL workspace, schema exploration, and result review. It makes the generated SQL visible so an analyst can inspect what ran instead of trusting an answer alone.

Project started 18 May 2026.

The application uses React 19, Vite 8, FastAPI, SQLAlchemy, psycopg 3, PostgreSQL 18 and SQLGlot. It supports Anthropic, OpenAI and Gemini through provider adapters. **SQL mode works without an API key.** AI mode requires a configured provider and model.

![Live natural-language query with executed SQL and PostgreSQL results](artifacts/screenshots/ai-query-desktop.png)

## Run locally with Docker

Requires Docker Desktop / Docker Engine with Compose. From the project root:

```powershell
# Only create .env if it does not already exist; preserve your existing credentials.
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d --build
```

Open [QueryLens](http://localhost:3000). The API is at [localhost:8000/docs](http://localhost:8000/docs). PostgreSQL is mapped to **127.0.0.1:5433**, avoiding an existing PostgreSQL installation on port 5432. All published ports bind to loopback.

Compose builds the frontend and serves it through Nginx, proxies `/v1` to the API, and waits for database/API health checks. The backend runs as a non-root user without development reload. The `pgdata18` volume persists sample database data. `docker compose stop` stops services without deleting that volume.

The included `readonly` / `readonly` and `admin` / `password` credentials belong to the **local synthetic sample database only**. They are not production credentials. No admin credential is used by the application.

## Try the application

1. Choose **SQL**, then **Top products by revenue**, and run the query. Results come from the actual PostgreSQL sample database; no model is used.
2. Inspect the executed SQL, sort table columns, and submit Yes/No feedback.
3. Open **Database schema** to inspect the eight tables/views and relationships.
4. Try `DELETE FROM customers` in SQL mode. It is blocked before database execution.
5. Open **Query history** to inspect recent inputs. Selecting a prior SQL result loads that SQL into the editor for an explicit rerun.
6. To use **Ask AI**, configure a provider key and that provider's supported model ID. Submit a specific question. If clarification is requested, choose an interpretation to regenerate the query. Each AI request can make several billable provider calls.

Results are capped at `MAX_ROWS` (default 1,000). The API's legacy `total_rows_available` field counts the bounded result, not an unbounded database total. Confidence is an uncalibrated review heuristic, not a probability that an answer is correct. Direct SQL results deliberately have no AI confidence score.

## Configuration

`.env.example` documents every setting; `env.example` is retained as a compatible copy. Settings load the repository `.env`, then `backend/.env`, with process environment variables taking precedence.

For Gemini, edit your local `.env` and replace the placeholder with your own key:

```dotenv
LLM_PROVIDER=gemini
GEMINI_API_KEY=ENTER_YOUR_GEMINI_API_KEY
LLM_MODEL_GEMINI=gemini-3.1-flash-lite
GEMINI_REASONING_EFFORT=low
ENABLE_AI_REVIEW=false
LLM_MAX_OUTPUT_TOKENS=1024
ENABLE_LIVE_EVALS=false
```

The placeholder is not a working credential. SQL mode requires no provider key. This Gemini model was verified for the local demonstration; availability depends on your provider account. After changing `.env`, recreate the backend with `docker compose up -d --no-deps --wait backend`, then run `docker compose restart frontend` to refresh its proxy connection.

Local `.env` files and environment variants are ignored by Git, including files inside `backend/`. Only the placeholder templates `.env.example` and `env.example` should be committed. Docker build contexts also exclude `.env*` files. Before pushing, inspect `git diff --cached` and confirm that no real keys or local environment files are staged. Never put a real key in either example template.

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Restricted PostgreSQL connection for both execution and introspection. Compose supplies its own internal service URL. |
| `LLM_PROVIDER` | `anthropic`, `openai`, or `gemini`. |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` | Key for the selected provider. Never commit these. |
| `LLM_MODEL_ANTHROPIC`, `LLM_MODEL_OPENAI`, `LLM_MODEL_GEMINI` | Explicit provider-supported model ID. No assumed model default. |
| `GEMINI_REASONING_EFFORT` | Gemini adapter setting, default `low`; compatibility depends on the selected model. |
| `LLM_TIMEOUT_SECONDS` | Per-provider-call timeout, default 30; automatic retries disabled. |
| `QUERY_TIMEOUT_SECONDS` | Database statement timeout, default 30. |
| `MAX_ROWS`, `MAX_SUBQUERY_DEPTH` | Result cap and nested subquery policy. |
| `MIN_CONFIDENCE_TO_EXECUTE` | Model-reported confidence gate before execution, default 0.3. Not a security control. |
| `HALLUCINATION_FLAG_THRESHOLD` | Overall heuristic score below which review is flagged. |
| `HISTORY_LIMIT` | Maximum in-memory history entries, default 100. |
| `ENABLE_LIVE_EVALS` | Default `false`; enabling permits costly live evaluation runs. |
| `ENABLE_AI_REVIEW` | Default `true`. Set `false` for a single generation call per question; SQL safety checks remain, but AI reviews and confidence scoring are skipped. |
| `LLM_MAX_OUTPUT_TOKENS` | Default `4096`, range 256–8192. The limited-quota screenshot configuration uses `1024`. |
| `CORS_ORIGINS` | JSON list of allowed development origins. |

AI prompts include the question, schema names/types/relationships and generated SQL. Result sanity checking also sends up to five result rows to the selected provider. Do not connect sensitive data without reviewing that data flow and your provider agreement. Column sample values are no longer gathered during schema inspection.

## Development without containerized frontend/backend

Use Python 3.13 and Node 22 (the container build uses Node 22). Start only the database, then use separate terminals:

```powershell
docker compose up -d postgres
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r backend/requirements.txt -r backend/requirements-dev.txt
$env:DATABASE_URL='postgresql+psycopg://readonly:readonly@127.0.0.1:5433/analytics'
.\venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

For macOS/Linux, use `python3`, `venv/bin/python`, `npm`, and `export DATABASE_URL=...`. Vite proxies `/v1` to port 8000. Stop the Compose frontend/backend before starting development servers on the same ports. Your existing `.env` can point to a different database; the explicit process override above selects the isolated sample database without editing it.

## Verification

From the project root (Python dependencies installed):

```powershell
# Deterministic unit/API tests; database tests explicitly skip unless enabled.
.\venv\Scripts\python.exe -m pytest -q -m 'not integration'
# Full suite against the local sample PostgreSQL database; no paid model calls.
$env:DATABASE_URL='postgresql+psycopg://readonly:readonly@127.0.0.1:5433/analytics'
$env:RUN_DB_TESTS='1'
.\venv\Scripts\python.exe -m pytest -q
.\venv\Scripts\python.exe -m ruff check backend/app tests
.\venv\Scripts\python.exe -m ruff format --check backend/app tests

npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix frontend run format:check
npm.cmd --prefix frontend run build
# Requires the actual app at port 3000 and installed Google Chrome:
npm.cmd --prefix frontend run test:e2e
# Recreate the real screenshot gallery:
cd frontend
node tests/capture.mjs
```

The browser suite includes real database journeys and one explicitly mocked transport test for clarification and failed feedback. The backend suite also tests the AI pipeline with a deterministic provider stub and real PostgreSQL execution. These tests do **not** verify a live model's semantic quality. CI is defined in `.github/workflows/checks.yml`; remote CI was not run during this local task.

## Database setup and migrations

`docker/init.sql` creates and seeds six tables and two views only when the Docker volume is empty. Existing volumes are not reseeded. Synthetic transactional data uses a fixed random seed for new initialization; different PostgreSQL versions can still produce different sample distributions.

The original `product_performance` view accidentally included order items from cancelled/refunded orders. Existing databases need the non-destructive view migration; new databases already include it:

```powershell
New-Item -ItemType Directory -Force artifacts/local-backups | Out-Null
docker compose exec -T postgres pg_dump -U admin -d analytics --schema-only --table=public.product_performance | Set-Content artifacts/local-backups/product_performance-before.sql
Get-Content docker/migrations/001_product_performance.sql -Raw | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U admin -d analytics
```

The migration uses a transaction and preserves rows and grants. `001_product_performance.rollback.sql` restores the old view logic; the schema backup can restore an independently customized view. Do not delete the Docker volume to apply this fix. The migration was applied to this task's local sample database.

## API

| Method | Path | Behavior |
| --- | --- | --- |
| POST | `/v1/query` | `{question, mode: "natural_language" or "sql", clarification_choice?}` → success, blocked, clarification_needed or error result. |
| GET | `/v1/schema` | Cached metadata; `?refresh=true` refreshes it. |
| GET | `/v1/history?limit=20` | Recent process-local history. |
| POST | `/v1/feedback` | `{query_id, is_correct, comment?}`; unknown/expired IDs return 404. |
| POST | `/v1/eval` | Explicitly enabled live smoke suite; disabled by default. |
| GET | `/v1/health` | Process liveness. |
| GET | `/v1/ready` | Database connectivity; returns 503 on failure. |
| GET | `/v1/config` | Non-secret UI capabilities and limits. |

Malformed requests return 422. Saturated query slots return 429. Query-domain failures return an explicit status in a 200 response so the UI can render the failed attempt. Unexpected transport failures use 5xx without exposing connection strings.

## Limits and deployment boundary

This is a **single-user local portfolio workbench**, not a public multi-tenant service. It has no authentication or per-user data isolation. History and feedback are bounded, shared within one API process and lost on restart. Use one API worker. Production container packaging is implemented, but public deployment requires authentication/authorization, durable isolated history, managed credentials, TLS, deployment-specific limits and operational review.

The SQL function allowlist is intentionally conservative and can reject legitimate analytical functions. Parser checks are defense in depth; restricted PostgreSQL privileges, read-only transactions and timeouts remain required. Confidence and alternative-query agreement can miss errors; matching bounded rows is not proof of correctness. Evaluations check result shape and refusals, not exact semantic answers or hallucination recall. No benchmark percentage is claimed.

After the initial audit, a user-authorized live smoke test succeeded on 16 October 2026 (IST) using `gemini-3.1-flash-lite`: one generation call, 1,801 input tokens and 115 output tokens, followed by real PostgreSQL execution returning five products. The [desktop screenshot](artifacts/screenshots/ai-query-desktop.png) shows the result. Local configuration uses `ENABLE_AI_REVIEW=false` and a 1,024-token output cap to conserve quota; no confidence score is assigned in this mode. This verifies one live journey, not general model accuracy. SQL mode remains available without credentials.

## Troubleshooting and further reading

- Database unavailable: inspect `docker compose ps` and `docker compose logs postgres backend`. Check port **5433** for host-side access; Compose uses port 5432 internally. A liveness response alone does not prove the database is ready.
- Port conflict: stop your development server before starting the production containers; do not stop unrelated services.
- Docker cannot start: resolve Docker Desktop's own startup failure first. This machine initially had a Docker inference-socket error; it recovered when Docker was started by the user.
- Model failure: verify the selected key, explicit model ID, account availability and model compatibility. No silent mock/fallback responses are returned.
- Missing history after restart is expected. Feedback for expired entries returns an error rather than falsely reporting success.

Read [ARCHITECTURE.md](ARCHITECTURE.md) and the [screenshot gallery](artifacts/screenshots/README.md) for the request flow and real application screens.
