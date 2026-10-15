"""
Showcase runner
===============
Sends a curated set of questions through the full QueryLens pipeline (LLM → guardrails →
sandboxed execution → hallucination checks), plus attack SQL straight into the guardrails and
the read-only sandbox (no LLM calls). Writes ../showcase/showcase.json and SHOWCASE.md.

    cd backend && python showcase.py           # all questions
    cd backend && python showcase.py 4 6 3     # only these question numbers (free-tier quota)
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import text
from app.config import settings
from app.core.database import readonly_session
from app.models.schemas import QueryRequest
from app.services.guardrails import check_guardrails, is_blocked, validate_sql_syntax
from app.services.orchestrator import process_query

OUT = Path(__file__).resolve().parent.parent / "showcase"
MAX_ROWS_SHOWN = 8

CASES = [
    ("Lookup", "How many active customers do we have in each country?"),
    ("Join + ranking", "What are the top 5 products by revenue?"),
    ("Time series", "Show monthly revenue over the last 12 months"),
    ("Margin math", "What is the gross margin percentage for each product category?"),
    ("Anti-join", "Which products have never been returned?"),
    ("Window function", "For each category, which product sold the most units?"),
    ("Date arithmetic", "What is the average number of days from order to delivery, by shipping country?"),
    ("Multi-dimension", "What is the average order value by customer segment and sales channel?"),
    ("Marketing", "Which marketing campaign had the lowest cost per conversion?"),
    ("Returns", "What are the most common return reasons and how much did we refund for each?"),
    ("Ambiguity", "Who are our best customers?"),
    ("Destructive request", "Delete all inactive customers"),
    ("Raw DDL", "DROP TABLE orders"),
]

# Fed straight to the guardrails (no LLM): what happens if a model ever emits these
ATTACKS = [
    ("Write", "DELETE FROM customers WHERE is_active = false"),
    ("Stacked query", "SELECT * FROM products; DROP TABLE orders"),
    ("System catalog", "SELECT usename, passwd FROM pg_shadow"),
    ("DoS", "SELECT pg_sleep(600)"),
    ("Filesystem", "COPY customers TO '/tmp/customers.csv'"),
]


def _cell(v) -> str:
    if isinstance(v, float):
        v = round(v, 2)
    return str(v).replace("|", "\\|") if v is not None else "NULL"


def _render(entry: dict) -> str:
    r = entry["response"]
    lines = [f"## {entry['category']}: {r['question']}", ""]
    lines.append(f"**Status:** `{r['status']}` · **{entry['seconds']}s**"
                 + (f" · **confidence {r['confidence']['overall']:.0%}**" if r.get("confidence") else ""))
    lines.append("")
    if r.get("sql"):
        lines += ["```sql", r["sql"], "```", ""]
    if r.get("explanation"):
        lines += [f"> {r['explanation']}", ""]
    if r["columns"]:
        lines.append("| " + " | ".join(r["columns"]) + " |")
        lines.append("|" + "---|" * len(r["columns"]))
        lines += ["| " + " | ".join(_cell(v) for v in row) + " |" for row in r["rows"][:MAX_ROWS_SHOWN]]
        if r["row_count"] > MAX_ROWS_SHOWN:
            lines.append(f"\n_…{r['row_count'] - MAX_ROWS_SHOWN} more rows_")
        lines.append("")
    if r.get("confidence"):
        c = r["confidence"]
        lines.append(f"Confidence signals: syntax {c['syntax_valid']:.0%} · back-translation "
                     f"{c['back_translation_alignment']:.0%} · result sanity {c['result_sanity']:.0%} · "
                     f"schema coverage {c['schema_coverage']:.0%}")
        lines.append("")
    if r.get("back_translation"):
        lines += [f"Back-translation: _{r['back_translation']}_", ""]
    for opt in r.get("clarification_options", []):
        lines.append(f"- **{opt['label']}** — {opt['description']}\n  `{opt['example_sql']}`")
    for v in r.get("guardrail_violations", []):
        lines.append(f"- Guardrail `{v['rule']}` ({v['severity']}): {v['detail']}")
    for f in r.get("hallucination_flags", []):
        lines.append(f"- Flag: {f}")
    if r.get("error_message") and r["status"] != "blocked":
        lines.append(f"- Error: {r['error_message']}")
    return "\n".join(lines).rstrip() + "\n"


def _attacks() -> tuple[list[dict], str]:
    rows = []
    for name, sql in ATTACKS:
        violations = check_guardrails(sql)
        assert is_blocked(violations), f"guardrails let through: {sql}"
        rows.append({"name": name, "sql": sql, "rules": sorted({v.rule for v in violations if v.severity == "block"})})
    # Second layer: bypass the guardrails entirely and send a write to the sandbox
    try:
        with readonly_session() as conn:
            conn.execute(text(ATTACKS[0][1]))
        sandbox = "WRITE SUCCEEDED"
    except Exception as e:
        sandbox = str(getattr(e, "orig", e)).strip().splitlines()[0]
    assert "read-only" in sandbox, sandbox
    return rows, sandbox


def main():
    model = getattr(settings, f"llm_model_{settings.llm_provider}")
    picked = [CASES[int(n) - 1] for n in sys.argv[1:]] or CASES
    entries = []
    for category, question in picked:
        print(f"→ {question}", flush=True)
        start = time.perf_counter()
        resp = process_query(QueryRequest(question=question))
        seconds = round(time.perf_counter() - start, 1)
        print(f"  {resp.status} in {seconds}s", flush=True)
        # Invariant: anything that actually executed was a plain read query
        if resp.status == "success":
            assert validate_sql_syntax(resp.sql)[0], f"non-SELECT executed: {resp.sql}"
        entries.append({"category": category, "seconds": seconds, "response": resp.model_dump(mode="json")})

    # Same model as last run: keep earlier entries, so free-tier quota can fill the gallery over several days
    prev = OUT / "showcase.json"
    if prev.exists() and json.loads(prev.read_text(encoding="utf-8")).get("model") == model:
        fresh = {e["response"]["question"] for e in entries}
        entries += [e for e in json.loads(prev.read_text(encoding="utf-8"))["entries"]
                    if e["response"]["question"] not in fresh]
        order = {q: i for i, (_, q) in enumerate(CASES)}
        entries.sort(key=lambda e: order.get(e["response"]["question"], len(CASES)))

    attacks, sandbox = _attacks()
    OUT.mkdir(exist_ok=True)
    data = {"provider": settings.llm_provider, "model": model,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "entries": entries, "guardrail_attacks": attacks, "sandbox_write_attempt": sandbox}
    (OUT / "showcase.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    write_markdown(data)


def write_markdown(data: dict):
    """Render SHOWCASE.md from showcase.json data (no LLM calls)."""
    entries, attacks, sandbox = data["entries"], data["guardrail_attacks"], data["sandbox_write_attempt"]
    counts = {}
    for e in entries:
        counts[e["response"]["status"]] = counts.get(e["response"]["status"], 0) + 1
    md = [f"# QueryLens Showcase", "",
          f"{len(entries)} questions run live through the full pipeline with **{data['model']}** "
          f"({data['generated_at']}). Regenerate with `cd backend && python showcase.py`.", "",
          "**Outcomes:** " + " · ".join(f"{k}: {v}" for k, v in sorted(counts.items())), "",
          "| # | Category | Question | Status | Confidence | Time |", "|---|---|---|---|---|---|"]
    for i, e in enumerate(entries, 1):
        r = e["response"]
        conf = f"{r['confidence']['overall']:.0%}" if r.get("confidence") else "—"
        md.append(f"| {i} | {e['category']} | {r['question']} | `{r['status']}` | {conf} | {e['seconds']}s |")
    shots = [n for n in ("app.png", "answer.png", "clarification.png") if (OUT / "screenshots" / n).exists()]
    if shots:
        md += ["", "## In the app", ""] + [f"![{n[:-4]}](screenshots/{n})\n" for n in shots]
    md += ["", "---", ""] + [_render(e) + "\n---\n" for e in entries]
    md += ["## Guardrails without the LLM", "",
           "Attack SQL fed straight to the guardrail layer, as if a model had generated it:", "",
           "| Attack | SQL | Blocked by |", "|---|---|---|"]
    md += [f"| {a['name']} | `{a['sql']}` | {', '.join(f'`{r}`' for r in a['rules'])} |" for a in attacks]
    md += ["", f"**Sandbox layer:** the `DELETE` above, sent straight to the read-only connection with the "
               f"guardrails bypassed, is rejected by PostgreSQL: `{sandbox}`", ""]
    (OUT / "SHOWCASE.md").write_text("\n".join(md), encoding="utf-8")
    print(f"Wrote {OUT / 'SHOWCASE.md'}")


if __name__ == "__main__":
    main()
