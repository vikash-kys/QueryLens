# QueryLens

**Ask a question about a PostgreSQL database, see the SQL behind the answer, and inspect the rows that came back.** QueryLens also has a direct SQL mode for users who prefer to write the query themselves. Both modes run through the same read-only execution path.

I started this project on **18 May 2026** to explore a practical problem with text-to-SQL systems: producing SQL is only the beginning. The application also needs to handle vague questions, prevent unsafe statements, show users what actually ran, and be honest when a result has not been fully checked.

![A live natural-language query showing generated SQL and PostgreSQL results](artifacts/screenshots/ai-query-desktop.png)

[See the desktop screenshot gallery](artifacts/screenshots/README.md) · [Read the architecture notes](ARCHITECTURE.md)

## What you can do

- **Ask in plain English.** QueryLens reads table, column, type, and foreign-key metadata from PostgreSQL and uses it to guide a configurable LLM. It validates the model's structured response before considering the SQL for execution.
- **Inspect the work.** A successful result shows the executed SQL, an explanation, the tables used, the returned rows, and any review notes. The table supports sorting and pagination.
- **Clarify an ambiguous request.** If the model cannot choose an interpretation, the UI presents options. The selected interpretation is sent with a new request; suggested SQL is never run simply because it appeared in an option.
- **Write SQL directly.** SQL mode works without an AI key. It still goes through query validation, row limiting, and the restricted database connection.
- **Explore and revisit.** The schema browser shows the connected database structure. Recent queries, outcomes, and Yes/No feedback are available in the UI. This history is bounded and kept in memory for the local demo.
- **See failures clearly.** Blocked writes, empty results, database errors, unavailable services, and disabled evaluations have distinct UI states.

## How a question becomes a result

```mermaid
flowchart LR
    Q[Question] --> S[Schema metadata]
    S --> L[Configured LLM]
    L --> V[Validate structured output]
    V --> G[SQLGlot SQL policy]
    G -->|allowed| E[Read-only PostgreSQL execution]
    G -->|blocked| B[Show reason]
    E --> R[Optional AI review]
    R --> U[SQL, rows, notes, and feedback in UI]
    D[Direct SQL] --> G
```

1. **Understand the database.** SQLAlchemy inspects the sample database and caches its schema metadata. The generation prompt receives names, types, and relationships, not sample row values.
2. **Generate or accept SQL.** In Ask AI mode, the selected Anthropic, OpenAI, or Gemini model returns SQL, an explanation, tables used, a model-reported confidence value, and possibly clarification options. In SQL mode, the user's statement enters at the next step.
3. **Check the statement.** SQLGlot parses PostgreSQL syntax into a tree. The policy allows a single SELECT or SELECT-based set query and rejects writes, locking, recursive queries, system-table access, and functions outside a deliberately narrow analytics allowlist. A low model-reported confidence value can also stop an AI query before execution; it is not a security boundary.
4. **Bound and execute it.** QueryLens caps the outer result with a configured LIMIT and validates the SQL again inside the executor. PostgreSQL receives it through a restricted account and a transaction set to READ ONLY. Connection and statement timeouts provide further limits. The transaction is rolled back when the request finishes.
5. **Return evidence.** The response contains the SQL that ran, column names, rows, execution time, and any warnings. `MAX_ROWS` defaults to 1,000; `total_rows_available` currently reports the bounded result, not a separate count of the entire database result set.

The parser, account permissions, transaction mode, and timeouts cover different failure modes. None makes arbitrary SQL or untrusted database access safe by itself. The function allowlist can reject legitimate advanced analysis, which is an intentional limit of this demo.

For example, the live screenshot starts with “Show the five most expensive products: name, category and unit price.” The model returned:

```sql
SELECT p.name, p.category, p.unit_price FROM products AS p ORDER BY p.unit_price DESC LIMIT 5
```

QueryLens executed that statement against the sample database and displayed five product rows. The screenshot shows the question, actual SQL, explanation, and results together so a reader can check the answer rather than seeing an unsupported summary.

## Reviewing AI answers

With `ENABLE_AI_REVIEW=true` (the default), QueryLens runs several checks after the primary query:

| Signal | What it checks |
| --- | --- |
| SQL syntax | Whether the candidate parsed as an allowed SELECT query. |
| Back-translation and alignment | An LLM describes what the SQL answers, then compares that description with the original question. |
| Result sanity | Local checks look for empty or NULL-heavy results and implausible numeric values; an LLM can inspect up to five returned rows. |
| Schema coverage | A keyword heuristic checks whether the reported tables fit the question. |
| Alternative-query agreement | If alignment is below 0.85, another generated query may be executed and its bounded rows compared with the primary result. If this check was not run, its score remains unmeasured. |

These signals produce review notes and a **heuristic** confidence breakdown. A high score does not prove the SQL answers the question. Agreement on a limited set of rows does not prove semantic correctness either. AI review can require multiple provider calls and may send a small sample of returned rows to that provider; review this data flow before connecting sensitive data.

For a limited API budget, set `ENABLE_AI_REVIEW=false`. Each Ask AI submission then makes one generation call, while SQL policy and restricted execution still run. The UI explicitly says the extra review was skipped and assigns **no confidence score**. `LLM_MAX_OUTPUT_TOKENS` sets a per-call output cap; SDK automatic retries are disabled.

## The sample database

The Docker setup seeds a synthetic e-commerce database with six tables and two views:

| Object | Used for |
| --- | --- |
| `customers` | Customer segment, country, and account status. |
| `products` | Catalog, category, current price, cost, and stock. |
| `orders` | Order status, dates, channel, and customer relationship. |
| `order_items` | Products and quantities in each order, including the price at purchase. |
| `returns` | Return requests, reasons, and refunds. |
| `marketing_campaigns` | Spend, clicks, conversions, and campaign dates. |
| `revenue_by_month` | Monthly revenue summaries. |
| `product_performance` | Product revenue and unit summaries, excluding cancelled and refunded orders. |

The seed data is for local demonstration. Docker persists it in the `pgdata18` volume. A new volume runs `docker/init.sql`; an existing volume is not automatically reseeded. If you have an older QueryLens volume, apply [the product-performance view migration](docker/migrations/001_product_performance.sql) after backing up your current view. The [rollback script](docker/migrations/001_product_performance.rollback.sql) restores the earlier logic.

## Technology

| Part | Implementation |
| --- | --- |
| API and models | Python 3.13, FastAPI, and Pydantic for request and response validation. |
| Database | PostgreSQL 18, SQLAlchemy for schema inspection and connections, and psycopg for the driver. |
| SQL policy | SQLGlot parsing, a restricted database account, read-only transactions, and statement limits. |
| Model adapters | Anthropic SDK; OpenAI SDK for OpenAI and Gemini's OpenAI-compatible endpoint. |
| Interface | React 19 and Vite 8, with a responsive workspace for queries, schema, history, and evaluations. |
| Local packaging | Docker Compose and Nginx, with loopback-bound ports. |

## Run locally

You need Docker Desktop or Docker Engine with Compose. An API key is **optional** for SQL mode. From the repository root:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d --build
```

On macOS or Linux, use `cp .env.example .env` for the first command. Open [the application](http://localhost:3000) or [the API documentation](http://localhost:8000/docs). The sample PostgreSQL server is available to the host at `127.0.0.1:5433`; containers use port 5432 internally. All published ports bind to loopback.

A first tour:

1. Choose **SQL**, run the suggested top-products query, and inspect its SQL and results.
2. Open **Database schema** to see the tables, views, and relationships.
3. Try `DELETE FROM customers` in SQL mode to see a blocked statement.
4. Open **Query history** and inspect the recorded outcome.
5. Add a supported provider key and model ID if you want to try **Ask AI**. Ask a specific question, such as “Show the five most expensive products with their category and price.”

The included `admin` / `password` and `readonly` / `readonly` credentials are for the isolated **sample database only**. The application uses the restricted account; it does not use the admin account to serve queries. Change these credentials and add access controls before adapting this setup for any real data or public service.

## Configure a model

`.env.example` lists the settings. Copy it to the ignored `.env`, then set `LLM_PROVIDER`, the corresponding API key, and an explicit provider-supported model ID. QueryLens has adapters for **Anthropic, OpenAI, and Gemini**; no provider/model pair is hard-coded as a universally available default.

For example, a small-budget Gemini configuration is:

```dotenv
LLM_PROVIDER=gemini
GEMINI_API_KEY=ENTER_YOUR_GEMINI_API_KEY
LLM_MODEL_GEMINI=gemini-3.1-flash-lite
GEMINI_REASONING_EFFORT=low
ENABLE_AI_REVIEW=false
LLM_MAX_OUTPUT_TOKENS=1024
ENABLE_LIVE_EVALS=false
```

Replace the key placeholder in your local `.env`; it is **not a working credential**. Model access varies by account. `.env` and its local variants are ignored by Git, while the example templates contain placeholders. After editing `.env`, reload the backend with `docker compose up -d --no-deps --wait backend` and restart the frontend proxy with `docker compose restart frontend`.

Other useful settings:

| Setting | Default | Purpose |
| --- | --- | --- |
| `MAX_ROWS` | `1000` | Maximum returned rows and outer SQL LIMIT. |
| `QUERY_TIMEOUT_SECONDS` | `30` | PostgreSQL statement timeout. |
| `LLM_TIMEOUT_SECONDS` | `30` | Timeout for one provider call. |
| `LLM_MAX_OUTPUT_TOKENS` | `4096` | Maximum provider output tokens, configurable from 256 to 8192. |
| `MAX_SUBQUERY_DEPTH` | `3` | Maximum allowed nested subqueries. |
| `MIN_CONFIDENCE_TO_EXECUTE` | `0.3` | Pre-execution gate for model-reported confidence. |
| `HALLUCINATION_FLAG_THRESHOLD` | `0.5` | Review-score threshold for a warning; not a correctness guarantee. |
| `HISTORY_LIMIT` | `100` | Maximum in-memory query records. |
| `ENABLE_LIVE_EVALS` | `false` | Explicit switch for provider-consuming evaluations. |
| `CORS_ORIGINS` | Local port 3000 origins | Allowed browser origins. |

Process environment variables override the root `.env`; `backend/.env` is also supported. Docker Compose supplies its own internal `DATABASE_URL` for the backend.

For local development outside the application containers, start only PostgreSQL with `docker compose up -d postgres`. Use Python 3.13 with the backend requirements and run `uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload`, setting `DATABASE_URL` to `postgresql+psycopg://readonly:readonly@127.0.0.1:5433/analytics`. In a second terminal, run `npm ci` and `npm run dev` from `frontend/`. Stop the Compose frontend and backend first so they do not occupy the same ports.

## Evaluations and verification

The app includes a **30-case** live evaluation suite covering lookups, joins, aggregates, dates, and attempted unsafe statements. It is disabled by default because running it can make many model requests. When enabled, `POST /v1/eval` reports column and row-shape checks, guardrail refusals, flags, and average heuristic confidence. These checks are useful smoke tests; they do **not** prove exact answer accuracy. No percentage from the earlier README is claimed for this version.

The local verification completed for this version included **54 backend/database tests** and **seven browser tests**. The backend tests cover SQL policy, bounded execution, provider failure handling, the query pipeline, and PostgreSQL behavior. The browser tests cover real database flows and one clearly marked mocked transport case for clarification and failed feedback. Ruff, ESLint, type checking, formatting checks, and the frontend build also passed locally. CI is defined in [the GitHub workflow](.github/workflows/checks.yml); its status should be checked separately on GitHub.

```powershell
# From the repository root, after installing backend requirements.
$env:DATABASE_URL='postgresql+psycopg://readonly:readonly@127.0.0.1:5433/analytics'
$env:RUN_DB_TESTS='1'
.\venv\Scripts\python.exe -m pytest -q
.\venv\Scripts\python.exe -m ruff check backend/app tests
.\venv\Scripts\python.exe -m ruff format --check backend/app tests

npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix frontend run format:check
npm.cmd --prefix frontend run build
npm.cmd --prefix frontend run test:e2e
```

For a Python development environment, create `venv` with Python 3.13 and install `backend/requirements.txt` plus `backend/requirements-dev.txt`. Use Node 22 for the frontend. Browser tests require the running application and an installed Google Chrome. The test suite does not make live model calls.

One user-authorized live smoke test **did** exercise Ask AI on 16 October 2026 (IST): Gemini 3.1 Flash-Lite generated SQL for the five most expensive products, and the real sample PostgreSQL database returned five rows. It used one generation request with **1,801 input and 115 output tokens** in single-call mode. The [captured result](artifacts/screenshots/ai-query-desktop.png) is a real browser screenshot. This checks one end-to-end path, not model quality across the 30 evaluation cases.

## API at a glance

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/v1/query` | Ask a question or submit SQL; returns `success`, `blocked`, `clarification_needed`, or `error`. |
| `GET` | `/v1/schema` | Read cached database metadata; `?refresh=true` updates the cache. |
| `GET` | `/v1/history?limit=20` | Read recent process-local requests. |
| `POST` | `/v1/feedback` | Mark a known query correct or incorrect; an unknown ID returns 404. |
| `POST` | `/v1/eval` | Run the live suite only when explicitly enabled. |
| `GET` | `/v1/health` | Process liveness. |
| `GET` | `/v1/ready` | Database readiness. |
| `GET` | `/v1/config` | Non-secret UI capabilities and limits. |

A direct SQL request needs no provider key:

```json
{
  "mode": "sql",
  "question": "SELECT name, category, unit_price FROM products ORDER BY unit_price DESC LIMIT 5"
}
```

For Ask AI, use `"mode": "natural_language"` (or omit `mode`) and put the question in `question`. A clarification response contains options; send the selected interpretation as `clarification_choice` with the follow-up request. The response shows the final SQL and rows on success. Query errors return an explicit status for the UI; unexpected transport errors use HTTP 5xx without exposing connection strings.

## Scope and limits

QueryLens is a **local, single-user portfolio application**. Its Docker setup builds the frontend for Nginx and runs a non-root FastAPI backend, but it is not a public multi-user deployment. There is no login, per-user isolation, persistent feedback/history, TLS termination, or deployment-specific rate limiting. History is shared within one API process and disappears on restart.

A generated query can be syntactically safe yet answer the wrong question. The AI review signals are useful warnings, not verified truth. Live evaluations test shapes and refusals rather than full semantic equivalence. The most reliable way to assess a result is to read the executed SQL alongside the returned data.

To stop the local stack without removing sample data, run `docker compose stop`. Avoid `docker compose down -v` unless you intend to delete the sample database volume.
