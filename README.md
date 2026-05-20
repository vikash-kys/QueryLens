# QueryLens · Text-to-SQL with Guardrails & Hallucination Detection

A production-grade natural language to SQL system that translates plain English questions into SQL, executes them safely, and validates correctness before showing results.

**Eval numbers (on the included golden test suite):**
- **~85% execution accuracy** — results match expected output
- **100% guardrail effectiveness** — zero destructive queries executed
- **Multi-signal hallucination detection** — back-translation + sanity checks + multi-query validation

---

## Architecture

```
User Question
     │
     ▼
┌─────────────────────────┐
│   Schema Extractor       │  Auto-introspects PostgreSQL: tables, columns,
│   (SQLAlchemy)           │  types, FK relationships, comments, sample values
└────────────┬────────────┘
             │ schema context
             ▼
┌─────────────────────────┐
│   SQL Generator          │  Few-shot prompted LLM (Claude Sonnet / GPT-4o)
│   (LLM + structured     │  Returns: SQL, explanation, confidence, tables used
│    output)               │  Detects ambiguity → asks for clarification
└────────────┬────────────┘
             │ candidate SQL
             ▼
┌─────────────────────────┐
│   Guardrail Middleware   │  Blocks: DDL, DML writes, system tables,
│   (7 configurable rules) │  dangerous patterns, injection attempts
└────────────┬────────────┘
             │ safe SQL (or BLOCKED)
             ▼
┌─────────────────────────┐
│   Executor               │  Read-only transaction + SELECT-only DB user
│   (PostgreSQL sandbox)   │  Auto-injects LIMIT, captures EXPLAIN plan
└────────────┬────────────┘
             │ results
             ▼
┌─────────────────────────┐
│   Hallucination Detector │  1. Back-translation alignment scoring
│   (4 signals)            │  2. Result sanity checks (NULLs, ranges, scale)
│                          │  3. Multi-query validation (two approaches)
│                          │  4. Schema coverage heuristic
└────────────┬────────────┘
             │ confidence score + flags
             ▼
        API Response
```

---

## Guardrails (7 rules)

| Rule | Action | Details |
|------|--------|---------|
| `NO_DDL` | Block | CREATE, ALTER, DROP, TRUNCATE, GRANT |
| `NO_WRITE_DML` | Block | INSERT, UPDATE, DELETE, MERGE |
| `DANGEROUS_PATTERN` | Block | Regex match: DROP TABLE, pg_shadow, xp_cmdshell, etc. |
| `SUBQUERY_DEPTH` | Warn | Max nesting depth configurable |
| `NO_LIMIT` | Warn | Auto-injects `LIMIT 1000` |
| `SYSTEM_TABLE_ACCESS` | Block | pg_catalog, information_schema, pg_stat |
| DB permissions | Implicit | SELECT-only user + READ ONLY transaction = double defense |

---

## Hallucination Detection Signals

```
Confidence = weighted sum of:
  ├── Syntax Valid (15%)          — sqlparse validates structure
  ├── Back-Translation (35%)      — LLM re-interprets SQL → question alignment
  ├── Result Sanity (25%)         — NULL checks, value ranges, row count plausibility
  └── Schema Coverage (10%)       — Did query touch expected tables?
```

Multi-query validation (generates two independent SQL approaches and compares results) runs when confidence is borderline.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11 |
| API | FastAPI |
| Database | PostgreSQL 16 |
| ORM/Introspection | SQLAlchemy 2.0 |
| LLM | Claude Sonnet 4 or GPT-4o |
| SQL Parsing | sqlparse |
| Frontend | React + Vite |
| Containerization | Docker + docker-compose |

---

## Quick Start

### Prerequisites
- Docker & docker-compose
- API key for your chosen LLM Provider (Anthropic, Gemini, or OpenAI)

### 1. Clone and configure

```bash
git clone <repo>
cd text2sql
cp .env.example .env
# Edit .env: set LLM_PROVIDER and replace placeholders with your actual API key(s)
```

### 2. Start everything

```bash
docker-compose up --build
```

- **Frontend**: http://localhost:3000
- **API docs**: http://localhost:8000/docs
- **PostgreSQL**: localhost:5432

### 3. Try it

Open http://localhost:3000 and ask:
- "What are the top 5 products by revenue?"
- "Show me monthly revenue for 2024"
- "Which customers have never placed an order?"
- "DELETE FROM customers" ← gets blocked by guardrails

---

## API Endpoints

```
POST /v1/query          Natural language → SQL → results
GET  /v1/schema         Database schema
GET  /v1/history        Recent query history
POST /v1/feedback       Mark result correct/incorrect
GET  /v1/eval           Run automated evaluation suite
GET  /docs              Swagger UI
```

### Query request

```json
POST /v1/query
{
  "question": "What are the top 5 products by revenue?"
}
```

### Query response

```json
{
  "query_id": "uuid",
  "question": "...",
  "sql": "SELECT p.name, SUM(...) AS revenue FROM ...",
  "explanation": "Joins products and order_items to sum revenue...",
  "columns": ["name", "revenue"],
  "rows": [["ProBook 15 Laptop", 58498.55], ...],
  "row_count": 5,
  "execution_time_ms": 12.4,
  "confidence": {
    "syntax_valid": 1.0,
    "back_translation_alignment": 0.94,
    "result_sanity": 0.92,
    "schema_coverage": 0.85,
    "overall": 0.87
  },
  "guardrail_violations": [],
  "hallucination_flags": [],
  "tables_used": ["products", "order_items", "orders"],
  "status": "success"
}
```

---

## Database Schema

The included PostgreSQL database has a realistic e-commerce dataset:

| Table | Rows | Description |
|-------|------|-------------|
| `customers` | 20 | Registered customers across countries |
| `products` | 20 | Product catalog with pricing and cost |
| `orders` | ~500 | Customer orders with status/channel |
| `order_items` | ~1800 | Line items per order |
| `returns` | ~80 | Return/refund requests |
| `marketing_campaigns` | 10 | Campaign performance metrics |

Plus two convenience views: `revenue_by_month`, `product_performance`.

---

## Local Development (without Docker)

```bash
# Backend
cd backend
pip install -r requirements.txt
# Set DATABASE_URL and ANTHROPIC_API_KEY in env
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

---

## Running Evals

```bash
curl http://localhost:8000/v1/eval | python3 -m json.tool
```

Or click "Evals" in the sidebar and press "Run Evals".

The suite tests 30 cases across: simple lookups, JOINs, aggregations, date filters, complex multi-table queries, and 5 guardrail cases (all must be blocked).

---

## Configuration

All settings in `backend/app/config.py` or via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `anthropic` | `anthropic`, `openai`, or `gemini` |
| `GEMINI_API_KEY` | — | Gemini API key |
| `ANTHROPIC_API_KEY` | — | Claude API key |
| `OPENAI_API_KEY` | — | GPT-4o API key |
| `MAX_ROWS` | `1000` | Row cap injected into queries |
| `QUERY_TIMEOUT_SECONDS` | `30` | PostgreSQL statement timeout |
| `MIN_CONFIDENCE_TO_EXECUTE` | `0.3` | Block queries below this confidence |
| `HALLUCINATION_FLAG_THRESHOLD` | `0.5` | Flag queries below this alignment score |

---

## Security Model

- **Application layer**: 7 guardrail rules inspect SQL before execution
- **Database layer**: `readonly` user has `SELECT` permissions only
- **Transaction layer**: All queries run in `SET TRANSACTION READ ONLY` — automatic rollback
- **Timeout**: 30-second statement timeout prevents DoS via expensive queries
- **Row cap**: Auto-injected `LIMIT` prevents accidental full-table dumps

Three independent layers mean even a hypothetical guardrail bypass cannot cause data modification.

---

## License

This project is **proprietary** and protected under copyright law. It is made available strictly for **educational, personal learning, and portfolio demonstration purposes**.

- **No Copying or Redistribution**: Copying, duplicating, cloning, distributing, or publishing this codebase (in whole or in part) for any other purpose is strictly prohibited.
- **All Rights Reserved**: All intellectual property rights are reserved by the copyright holder.

For complete terms and conditions, please refer to the [LICENSE](file:///d:/text-sql-query/QueryLens/LICENSE) file in the root directory.
