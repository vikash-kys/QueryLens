# QueryLens · Production-Grade Text-to-SQL with Guardrails & Hallucination Detection

QueryLens is a production-grade, secure, natural-language-to-SQL system that auto-introspects a PostgreSQL database, translates plain English queries using state-of-the-art LLMs, validates queries against complex safety guardrails, executes them in a sandboxed, read-only transaction, and checks results using a multi-signal hallucination detection engine before returning them.

**Evaluation Suite Results (on the included 30-case golden test suite):**
* **~85% Execution Accuracy** — Results match expected output exactly on complex queries and aggregates.
* **100% Guardrail Effectiveness** — Zero destructive or system-level queries executed.
* **Multi-Signal Hallucination Detection** — Dynamic verification using 5 weighted confidence indicators.

---

## Screenshots

| Home — Ready State | Successful Query + Confidence Scoring |
|---|---|
| ![QueryLens home state](showcase/screenshots/querylens_home_light.png) | ![Query result with confidence ring and data table](showcase/screenshots/querylens_result_light.png) |

| Guardrails Blocking + Clarification Flow | 30-Case Evaluation Dashboard |
|---|---|
| ![Guardrail blocking a DELETE with clarification options](showcase/screenshots/querylens_guardrail_light.png) | ![Evaluation dashboard showing 85% accuracy and 100% guardrail effectiveness](showcase/screenshots/querylens_evals_light.png) |

---

## Key Features

1. **Multi-Provider LLM Integration**: Native support for **Anthropic Claude** (Claude Sonnet 5.5), **OpenAI** (GPT-6 Astra), and **Google Gemini** (Gemini 3.8 Flash, via Gemini's OpenAI-compatible API layer). Any model is overridable via env vars.
2. **Double-Defense Sandboxed Execution**: Secure execution leveraging database-level `SELECT`-only roles combined with transaction-level `SET TRANSACTION READ ONLY` and auto-rollback to ensure absolute safety.
3. **Six Active Security Guardrails**: Deep AST (Abstract Syntax Tree) and regex inspection that warns or blocks DDL, write operations, system catalogs, and subquery nesting issues.
4. **5-Signal Confidence Engine**: A comprehensive scoring algorithm integrating SQL syntax validation, back-translation alignment, rule/LLM-based result sanity checks, schema keyword coverage, and alternative approach multi-query validation.
5. **Ambiguity & Clarification Flow**: When a question is ambiguous, QueryLens generates structured clarification options, rendering them in the frontend so users can choose the exact query they want.
6. **Active Feedback Loop**: Users can mark generated queries as correct/incorrect (`Yes`/`No`), recording audit feedback to backend storage.
7. **Interactive Evaluation Dashboard**: Runs a suite of 30 golden test cases directly from the React sidebar, graphing key performance metrics.

---

## System Architecture

```
User Question
     │
     ▼
┌─────────────────────────┐
│   Schema Extractor       │  Auto-introspects PostgreSQL: tables, columns,
│   (SQLAlchemy 2.0)       │  types, FK relationships, comments, sample values
└────────────┬────────────┘
             │ schema context
             ▼
┌─────────────────────────┐
│   SQL Generator          │  Few-shot prompted LLM (Claude / GPT / Gemini)
│   (LLM + structured     │  Returns: SQL, explanation, confidence, tables used.
│    output)               │  Detects ambiguity → asks for clarification.
└────────────┬────────────┘
             │ candidate SQL
             ▼
┌─────────────────────────┐
│   Guardrail Middleware   │  Blocks: DDL, DML writes, system tables,
│   (AST + Regex Rules)    │  dangerous patterns, injection attempts.
└────────────┬────────────┘
             │ safe SQL (or BLOCKED)
             ▼
┌─────────────────────────┐
│   Executor               │  Read-only transaction + SELECT-only DB user.
│   (PostgreSQL sandbox)   │  Auto-injects LIMIT, captures EXPLAIN plan.
└────────────┬────────────┘
             │ results
             ▼
┌─────────────────────────┐
│   Hallucination Detector │  1. Back-translation alignment scoring
│   (5 weighted signals)   │  2. Result sanity checks (NULLs, ranges, scale)
│                          │  3. Multi-query validation (two approaches)
│                          │  4. Schema coverage heuristic
└────────────┬────────────┘
             │ confidence score + flags
             ▼
        API Response
```

---

## Double-Defense Safety Guardrails

QueryLens uses a multi-layered security model protecting database integrity:

| Rule | Action | Details |
|------|--------|---------|
| `NO_DDL` | **Block** | Rejects `CREATE`, `ALTER`, `DROP`, `TRUNCATE`, `RENAME`, `COMMENT`, `GRANT`, `REVOKE` |
| `NO_WRITE_DML` | **Block** | Rejects `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `UPSERT`, `REPLACE` |
| `DANGEROUS_PATTERN` | **Block** | Regex checks blocking semicolon injection, comment masking, system execution (`xp_cmdshell`), filesystem copy, and DoS attempts (`pg_sleep`) |
| `SYSTEM_TABLE_ACCESS` | **Block** | Blocks access to `pg_catalog`, `information_schema`, `pg_stat`, `pg_shadow`, `pg_user` |
| `SUBQUERY_DEPTH` | **Warn** | Detects deep nested structures (`max_subquery_depth`) and warns users to simplify |
| `NO_LIMIT` | **Warn** | Detects missing row limits, warning users and auto-injecting a configured `LIMIT 1000` |
| **DB Layer Protection** | **Implicit** | Connected using a `readonly` user with `SELECT` permission only |
| **Transaction Sandbox** | **Implicit** | All SQL queries are executed in a `SET TRANSACTION READ ONLY` transaction blocks with automatic rollbacks |

---

## Hallucination Detection & Confidence Scoring

Confidence is calculated as a weighted combination of 5 signals (totaling 100%):

```
Confidence Breakdown:
  ├── Syntax Valid (15%)          — sqlparse validates AST structure
  ├── Back-Translation (35%)      — LLM re-interprets SQL → question alignment
  ├── Result Sanity (25%)         — Compares column values, NULL count percentages, and LLM sanity checks
  ├── Schema Coverage (10%)       — Heuristic matching user prompt terms to database tables used
  └── Multi-Query Agreement (15%)  — Triggers an alternative SQL generation approach to cross-check outputs
```

If the back-translation or multi-query agreement flags borderline results, dynamic warnings and hallucination flags are returned to the user in the UI.

---

## Technology Stack

* **Backend Framework**: Python 3.13 + FastAPI
* **Database**: PostgreSQL 18 (realistic e-commerce layout)
* **Introspection Engine**: SQLAlchemy 2.1 + psycopg 3
* **Supported LLMs**:
  * **Anthropic**: Claude Sonnet 5.5 (`claude-sonnet-5-5` default)
  * **OpenAI**: GPT-6 Astra (`gpt-6-astra` default)
  * **Google**: Gemini 3.8 Flash (`gemini-3.8-flash` default)
* **SQL Parsing**: `sqlparse`
* **Frontend**: React 19 + Vite 8 (dynamic dashboard with real-time SQL syntax highlighting, confidence rings, sorting, pagination, and history panels)

---

## Configuration Variables

Configuration settings are loaded from `backend/app/config.py` or `.env`:

| Environment Variable | Default | Description |
|----------------------|---------|-------------|
| `LLM_PROVIDER` | `anthropic` | `anthropic`, `openai`, or `gemini` |
| `ANTHROPIC_API_KEY` | *(Optional)* | Claude API Key |
| `OPENAI_API_KEY` | *(Optional)* | OpenAI API Key |
| `GEMINI_API_KEY` | *(Optional)* | Google Gemini API Key |
| `LLM_MODEL_ANTHROPIC` | `claude-sonnet-5-5` | Target model for Anthropic requests |
| `LLM_MODEL_OPENAI` | `gpt-6-astra` | Target model for OpenAI requests |
| `LLM_MODEL_GEMINI` | `gemini-3.8-flash` | Target model for Gemini requests |
| `GEMINI_REASONING_EFFORT` | `low` | Gemini thinking effort (`low` ≈ 2s per call; `medium`/`high` trade latency for depth) |
| `DATABASE_URL` | `postgresql://readonly:readonly@localhost:5432/analytics` | Target database connection for query execution |
| `ADMIN_DATABASE_URL` | `postgresql://admin:password@localhost:5432/analytics` | Database connection used by Schema Extractor |
| `MAX_ROWS` | `1000` | Row cap auto-injected into generated SELECT statements |
| `MAX_SUBQUERY_DEPTH` | `3` | Maximum permitted subquery nesting depth |
| `QUERY_TIMEOUT_SECONDS` | `30` | Maximum timeout for SQL query execution |
| `MIN_CONFIDENCE_TO_EXECUTE` | `0.3` | Safety threshold to block execution for low-confidence SQL |
| `HALLUCINATION_FLAG_THRESHOLD` | `0.5` | Threshold score to flag potential hallucinations |

---

## Database Schema Details

The bundled PostgreSQL database container is seeded with a highly realistic, pre-populated e-commerce schema:

| Table Name | Description / Sample Columns |
|------------|-----------------------------|
| `customers` | Account data: country, email, active status, customer segment |
| `products` | E-commerce catalog: cost, unit price, stock quantity, category |
| `orders` | Customer order records: created timestamp, status, delivery dates |
| `order_items` | Products within an order: quantity, unit price, discount percentage |
| `returns` | Refund and returns data: return reason, refund amount, return date |
| `marketing_campaigns` | Campaign metrics: ROI, spend, clicks, conversion rate |

Plus database views: `revenue_by_month`, `product_performance`.

---

## Quick Start Guide

### Prerequisites
* Docker & Docker Compose
* An API key for your chosen provider (Anthropic, OpenAI, or Gemini)

### 1. Configure the Environment
Clone this repository, copy the template `.env` file, and fill in your API key:
```bash
cp env.example .env
```
Edit `.env`:
```env
LLM_PROVIDER=gemini # Or "anthropic" / "openai"
GEMINI_API_KEY=your_gemini_api_key
# ANTHROPIC_API_KEY=your_anthropic_api_key
# OPENAI_API_KEY=your_openai_api_key
```

### 2. Start Services via Docker Compose
Start up the PostgreSQL instance (auto-seeded), backend API, and React frontend:
```bash
docker compose up --build
```
* **Frontend Dashboard**: [http://localhost:3000](http://localhost:3000)
* **Backend API Docs (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)
* **PostgreSQL Sandbox**: `localhost:5432` (`analytics` database)

### 3. Alternative Local Development (No Docker)
To run directly on your host machine:

**Backend Services**:
```bash
cd backend
pip install -r requirements.txt
# Settings load from the repo-root .env automatically
uvicorn app.main:app --reload
```

**Frontend Services**:
```bash
cd frontend
npm install
npm run dev
```

---

## Interactive Evaluation Suite

QueryLens includes an automated evaluation suite to ensure continuous model quality:
* **30 Golden Cases**: Tests range across simple lookups, complex JOINs, multi-table aggregations, date filter extractions, and 5 safety guardrail bypass attempts.
* **Direct UI Execution**: Click "Evals" in the frontend sidebar, and click **Run Evals** to run the suite, viewing execution passes, failures, and generated queries in real-time.
* **API Execution**:
  ```bash
  curl http://localhost:8000/v1/eval | python3 -m json.tool
  ```

---

## Showcase

[`showcase/SHOWCASE.md`](showcase/SHOWCASE.md) is a gallery of real pipeline runs: generated SQL, result rows, confidence signals, clarification and refusal behavior. It also includes attack SQL fed straight to the guardrails and a write sent directly to the read-only sandbox. Regenerate it with:

```bash
cd backend
python showcase.py          # all questions
python showcase.py 4 6 3    # only some, by number (free-tier Gemini keys allow ~20 requests/day per model)
```

Runs on the same model accumulate, so a free-tier key can fill the gallery over several days.

---

## API Endpoints Reference

```
POST /v1/query          Translate NL to SQL, validate, execute, check hallucinations
GET  /v1/schema         Retrieve autodetected database schema with comments & details
GET  /v1/history        Retrieve last 20 queries with feedback stats
POST /v1/feedback       Record user feedback (is_correct=true/false) on queries
GET  /v1/eval           Run the 30-case evaluation suite
GET  /v1/health         Check backend server health
```

### Standard Query API

#### Request (`POST /v1/query`)
```json
{
  "question": "What are the top 5 products by revenue?"
}
```

#### Response (Success Mode)
```json
{
  "query_id": "8b5fe1eb-66fa-4966-9bcf-1662fb16e16f",
  "question": "What are the top 5 products by revenue?",
  "sql": "SELECT p.name, SUM(oi.quantity * oi.unit_price) AS revenue FROM products p JOIN order_items oi ON oi.product_id = p.product_id GROUP BY p.name ORDER BY revenue DESC LIMIT 5",
  "explanation": "Calculates revenue by multiplying quantity and price from order items, grouped by product name.",
  "columns": ["name", "revenue"],
  "rows": [
    ["ProBook 15 Laptop", 58498.55],
    ["Wireless Headset", 12550.00]
  ],
  "row_count": 2,
  "total_rows_available": 2,
  "execution_time_ms": 11.2,
  "confidence": {
    "syntax_valid": 1.0,
    "back_translation_alignment": 0.95,
    "result_sanity": 0.9,
    "schema_coverage": 0.8,
    "overall": 0.91
  },
  "guardrail_violations": [],
  "hallucination_flags": [],
  "tables_used": ["products", "order_items"],
  "status": "success"
}
```

#### Response (Blocked Mode)
```json
{
  "query_id": "4b68e92f-d890-482d-8b30-3628e932b13c",
  "question": "DELETE FROM customers",
  "sql": "DELETE FROM customers",
  "status": "blocked",
  "guardrail_violations": [
    {
      "rule": "NO_WRITE_DML",
      "detail": "Write operation 'DELETE' is not permitted. Only SELECT queries are allowed.",
      "severity": "block"
    }
  ],
  "error_message": "Query blocked by safety guardrails. Write operation 'DELETE' is not permitted. Only SELECT queries are allowed."
}
```

#### Response (Ambiguous Query / Clarification Mode)
```json
{
  "query_id": "2d292bb0-b74a-44a6-a4c3-2a3cfefd8cb5",
  "question": "What is our revenue?",
  "status": "clarification_needed",
  "clarification_options": [
    {
      "label": "Gross revenue (all completed orders)",
      "description": "Total revenue from all non-cancelled/refunded orders",
      "example_sql": "SELECT SUM(oi.quantity * oi.unit_price) FROM order_items oi JOIN orders o ON o.order_id=oi.order_id WHERE o.status NOT IN ('cancelled','refunded')"
    },
    {
      "label": "Net revenue (after discounts)",
      "description": "Revenue accounting for discount percentages",
      "example_sql": "SELECT SUM(oi.quantity * oi.unit_price * (1 - oi.discount_pct/100)) FROM order_items oi JOIN orders o ON o.order_id=oi.order_id WHERE o.status NOT IN ('cancelled','refunded')"
    }
  ]
}
```
