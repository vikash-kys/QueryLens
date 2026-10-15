import "./components.css";
import { useState, useRef, useEffect } from "react";
import {
  Terminal,
  Shield,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Clock,
  Database,
  ChevronRight,
  RotateCcw,
  ThumbsUp,
  ThumbsDown,
  BarChart2,
  Loader2,
  Info,
  ChevronDown,
  ChevronUp,
  Layers,
  Zap,
} from "lucide-react";
import {
  queryNL,
  sendFeedback,
  getHistory,
  runEval,
  getSchema,
  getConfig,
  getReady,
} from "./lib/api.js";

// ─── Syntax Highlighter ───────────────────────────────────────────────
/** @param {{sql: string | null}} props */
function SqlHighlight({ sql }) {
  if (!sql) return null;
  const tokens = sql.split(
    /('(?:''|[^'])*'|\b(?:SELECT|FROM|WHERE|JOIN|LEFT|RIGHT|INNER|GROUP|ORDER|BY|HAVING|LIMIT|AND|OR|NOT|IN|AS|ON|DISTINCT|COUNT|SUM|AVG|MAX|MIN|CASE|WHEN|THEN|ELSE|END|WITH|NULL|IS|DESC|ASC)\b|\b\d+(?:\.\d+)?\b)/gi,
  );
  return (
    <pre className="sql-block">
      <code>
        {tokens.map((token, i) => (
          <span
            key={i}
            className={
              token.startsWith("'")
                ? "str"
                : /^\d/.test(token)
                  ? "num"
                  : /^[A-Z]+$/i.test(token)
                    ? "kw"
                    : ""
            }
          >
            {token}
          </span>
        ))}
      </code>
    </pre>
  );
}

// ─── Confidence Ring ───────────────────────────────────────────────────
/** @param {{score: number}} props */
function ConfidenceRing({ score }) {
  const pct = Math.round(score * 100);
  const r = 22,
    circ = 2 * Math.PI * r;
  const dash = (score * circ).toFixed(1);
  const color =
    score >= 0.8
      ? "var(--green)"
      : score >= 0.55
        ? "var(--yellow)"
        : "var(--red)";

  return (
    <div className="conf-ring" title={`Confidence: ${pct}%`}>
      <svg width="64" height="64" viewBox="0 0 64 64">
        <circle
          cx="32"
          cy="32"
          r={r}
          fill="none"
          stroke="var(--bg-4)"
          strokeWidth="4"
        />
        <circle
          cx="32"
          cy="32"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="4"
          strokeDasharray={`${dash} ${circ}`}
          strokeLinecap="round"
          transform="rotate(-90 32 32)"
          style={{ transition: "stroke-dasharray 0.6s ease" }}
        />
      </svg>
      <span className="conf-pct" style={{ color }}>
        {pct}%
      </span>
    </div>
  );
}

// ─── Confidence Breakdown ──────────────────────────────────────────────
/** @param {{confidence: import("./types").Confidence}} props */
function ConfidenceBreakdown({ confidence }) {
  if (!confidence) return null;
  const metrics = [
    { label: "Syntax Valid", value: confidence.syntax_valid },
    { label: "Back-Translation", value: confidence.back_translation_alignment },
    { label: "Result Sanity", value: confidence.result_sanity },
    { label: "Schema Coverage", value: confidence.schema_coverage },
    { label: "Alternative Agreement", value: confidence.multi_query_agreement },
  ];
  return (
    <div className="conf-breakdown">
      {metrics.map((m) => (
        <div key={m.label} className="conf-metric">
          <span className="conf-metric-label">{m.label}</span>
          <div className="conf-bar-track">
            <div
              className="conf-bar-fill"
              style={{
                width: `${(m.value ?? 0) * 100}%`,
                background:
                  (m.value ?? 0) >= 0.8
                    ? "var(--green)"
                    : (m.value ?? 0) >= 0.55
                      ? "var(--yellow)"
                      : "var(--red)",
              }}
            />
          </div>
          <span className="conf-metric-val">
            {m.value == null ? "Not measured" : `${Math.round(m.value * 100)}%`}
          </span>
        </div>
      ))}
    </div>
  );
}

// ─── Data Table ───────────────────────────────────────────────────────
/** @param {{columns: string[], rows: import("./types").Cell[][], totalRows: number}} props */
function ResultTable({ columns, rows, totalRows }) {
  const [sortCol, setSortCol] = useState(/** @type {number | null} */ (null));
  const [sortDir, setSortDir] = useState("asc");
  const [page, setPage] = useState(0);
  const PAGE = 20;

  /** @param {number} col */
  const toggleSort = (col) => {
    if (sortCol === col) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortCol(col);
      setSortDir("asc");
    }
    setPage(0);
  };

  let sorted = [...rows];
  if (sortCol !== null) {
    const idx = sortCol;
    sorted.sort((a, b) => {
      const va = a[idx],
        vb = b[idx];
      if (va === null) return 1;
      if (vb === null) return -1;
      const numA = Number(va),
        numB = Number(vb);
      const comp =
        !isNaN(numA) && !isNaN(numB)
          ? numA - numB
          : String(va).localeCompare(String(vb));
      return sortDir === "asc" ? comp : -comp;
    });
  }

  const pageRows = sorted.slice(page * PAGE, (page + 1) * PAGE);
  const totalPages = Math.ceil(sorted.length / PAGE);

  return (
    <div className="result-table-wrap">
      <div className="table-scroll">
        <table className="result-table">
          <thead>
            <tr>
              {columns.map((col, i) => (
                <th
                  key={i}
                  aria-sort={
                    sortCol === i
                      ? sortDir === "asc"
                        ? "ascending"
                        : "descending"
                      : "none"
                  }
                >
                  <button onClick={() => toggleSort(i)} className="sortable-th">
                    <span>{col}</span>
                    {sortCol === i &&
                      (sortDir === "asc" ? (
                        <ChevronUp size={11} />
                      ) : (
                        <ChevronDown size={11} />
                      ))}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageRows.map((row, ri) => (
              <tr key={ri}>
                {row.map((cell, ci) => (
                  <td key={ci} className={cell === null ? "null-cell" : ""}>
                    {cell === null ? (
                      <span className="null-val">NULL</span>
                    ) : (
                      String(cell)
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="table-footer">
        <span className="table-count">
          Showing {pageRows.length} of {rows.length} rows
          {totalRows > rows.length && ` (${totalRows.toLocaleString()} total)`}
        </span>
        {totalPages > 1 && (
          <div className="pagination">
            <button
              aria-label="Previous page"
              disabled={page === 0}
              onClick={() => setPage((p) => p - 1)}
            >
              ←
            </button>
            <span>
              {page + 1} / {totalPages}
            </span>
            <button
              aria-label="Next page"
              disabled={page >= totalPages - 1}
              onClick={() => setPage((p) => p + 1)}
            >
              →
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Query Result Card ────────────────────────────────────────────────
/** @param {{result: import("./types").QueryResult, onClarify: (q: string, choice: string) => Promise<void>, busy: boolean}} props */
function ResultCard({ result, onClarify, busy }) {
  const [sqlOpen, setSqlOpen] = useState(true);
  const [detailOpen, setDetailOpen] = useState(false);
  const [feedbackGiven, setFeedbackGiven] = useState(
    /** @type {boolean | null} */ (null),
  );

  const [feedbackError, setFeedbackError] = useState(
    /** @type {string | null} */ (null),
  );
  const [feedbackBusy, setFeedbackBusy] = useState(false);
  /** @param {boolean} correct */
  const handleFeedback = async (correct) => {
    setFeedbackBusy(true);
    setFeedbackError(null);
    try {
      await sendFeedback(result.query_id, correct);
      setFeedbackGiven(correct);
    } catch (err) {
      setFeedbackError(err instanceof Error ? err.message : "Feedback failed");
    } finally {
      setFeedbackBusy(false);
    }
  };

  const statusColor =
    {
      success: "var(--green)",
      blocked: "var(--red)",
      error: "var(--red)",
      clarification_needed: "var(--yellow)",
    }[result.status] || "var(--text-dim)";

  const conf = result.confidence?.overall;
  const confColor =
    conf == null
      ? undefined
      : conf >= 0.8
        ? "var(--green)"
        : conf >= 0.55
          ? "var(--yellow)"
          : "var(--red)";

  return (
    <div className="result-card">
      {/* Header */}
      <div className="result-header">
        <div className="result-question">
          <Terminal size={13} style={{ opacity: 0.5 }} />
          <span>{result.question}</span>
        </div>
        <div className="result-meta">
          <span
            className="status-badge"
            style={{ color: statusColor, borderColor: statusColor }}
          >
            {result.status.replace("_", " ")}
          </span>
          {result.execution_time_ms && (
            <span className="meta-chip">
              <Clock size={10} /> {result.execution_time_ms}ms
            </span>
          )}
        </div>
      </div>

      {/* Blocked */}
      {result.status === "blocked" && (
        <div className="alert-box red">
          <Shield size={14} />
          <div>
            <div className="alert-title">Query Blocked by Guardrails</div>
            {result.guardrail_violations
              .filter((v) => v.severity === "block")
              .map((v, i) => (
                <div key={i} className="alert-item">
                  ⊘ [{v.rule}] {v.detail}
                </div>
              ))}
          </div>
        </div>
      )}

      {/* Clarification */}
      {result.status === "clarification_needed" && (
        <div className="clarification-box">
          <div className="clar-title">
            <Info size={13} /> Ambiguous question — which did you mean?
          </div>
          {result.clarification_options.map((opt, i) => (
            <button
              key={i}
              className="clar-option"
              disabled={busy}
              onClick={() =>
                onClarify(result.question, opt.label + ": " + opt.description)
              }
            >
              <div className="clar-label">{opt.label}</div>
              <div className="clar-desc">{opt.description}</div>
              <span className="clar-action">Use this interpretation →</span>
            </button>
          ))}
        </div>
      )}

      {/* Error */}
      {result.status === "error" && (
        <div className="alert-box red">
          <XCircle size={14} />
          <div>{result.error_message}</div>
        </div>
      )}

      {/* Success */}
      {result.status === "success" && (
        <>
          {/* Guardrail warnings */}
          {result.guardrail_violations
            .filter((v) => v.severity === "warn")
            .map((v, i) => (
              <div key={i} className="alert-box yellow">
                <AlertTriangle size={12} />
                <span>
                  [{v.rule}] {v.detail}
                </span>
              </div>
            ))}

          {/* Hallucination flags */}
          {result.hallucination_flags.length > 0 && (
            <div className="alert-box yellow">
              <AlertTriangle size={13} />
              <div>
                <div className="alert-title">Review notes</div>
                {result.hallucination_flags.map((f, i) => (
                  <div key={i} className="alert-item">
                    ⚠ {f}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* SQL + Confidence row */}
          <div className="sql-conf-row">
            <div className="sql-section">
              <button
                className="section-toggle"
                onClick={() => setSqlOpen((o) => !o)}
              >
                <Database size={11} />
                Executed SQL
                {sqlOpen ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
              </button>
              {sqlOpen && <SqlHighlight sql={result.sql} />}
              {result.explanation && (
                <div className="explanation">{result.explanation}</div>
              )}
            </div>
            {result.confidence && (
              <div className="confidence-section">
                <ConfidenceRing score={result.confidence.overall} />
                <div className="conf-label" style={{ color: confColor }}>
                  {(conf ?? 0) >= 0.8
                    ? "High Confidence"
                    : (conf ?? 0) >= 0.55
                      ? "Medium Confidence"
                      : "Low Confidence"}
                </div>
              </div>
            )}
          </div>

          {/* Breakdown toggle */}
          {result.confidence && (
            <button
              className="detail-toggle"
              onClick={() => setDetailOpen((o) => !o)}
            >
              <Layers size={10} />
              {detailOpen ? "Hide" : "Show"} confidence breakdown
            </button>
          )}
          {detailOpen && result.confidence && (
            <ConfidenceBreakdown confidence={result.confidence} />
          )}

          {/* Tables used */}
          {result.tables_used?.length > 0 && (
            <div className="tables-used">
              <Zap size={10} />
              {result.tables_used.map((t) => (
                <span key={t} className="table-chip">
                  {t}
                </span>
              ))}
            </div>
          )}

          {/* Results table */}
          {result.row_count > 0 && (
            <ResultTable
              columns={result.columns}
              rows={result.rows}
              totalRows={result.total_rows_available}
            />
          )}
          {result.row_count === 0 && (
            <div className="empty-result">No rows returned</div>
          )}

          {/* Feedback */}
          <div className="feedback-row">
            {feedbackError && (
              <span role="alert" className="eval-error">
                {feedbackError}
              </span>
            )}
            <span className="feedback-label">Was this result correct?</span>
            {feedbackGiven === null ? (
              <>
                <button
                  className="fb-btn green"
                  disabled={feedbackBusy}
                  onClick={() => handleFeedback(true)}
                >
                  <ThumbsUp size={11} /> Yes
                </button>
                <button
                  className="fb-btn red"
                  disabled={feedbackBusy}
                  onClick={() => handleFeedback(false)}
                >
                  <ThumbsDown size={11} /> No
                </button>
              </>
            ) : (
              <span className="fb-thanks">
                {feedbackGiven ? (
                  <CheckCircle2 size={12} color="var(--green)" />
                ) : (
                  <XCircle size={12} color="var(--red)" />
                )}
                Feedback recorded
              </span>
            )}
          </div>
        </>
      )}
    </div>
  );
}

// ─── History Panel ────────────────────────────────────────────────────
/** @param {{onSelect: (q: string, mode: import("./types").Mode) => void}} props */
function HistoryPanel({ onSelect }) {
  const [items, setItems] = useState(
    /** @type {import("./types").HistoryItem[]} */ ([]),
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(/** @type {string | null} */ (null));

  useEffect(() => {
    getHistory(20)
      .then(setItems)
      .catch((e) => setError(e instanceof Error ? e.message : "Request failed"))
      .finally(() => setLoading(false));
  }, []);

  if (loading)
    return (
      <div className="hist-loading">
        <Loader2 size={14} className="spin" />
      </div>
    );

  return (
    <div className="history-panel">
      <h1>Query history</h1>
      <p className="page-description">
        Recent queries in this server session. Select one to review its input.
        History clears when the server restarts.
      </p>
      {error && (
        <p role="alert" className="eval-error">
          {error}
        </p>
      )}
      {items.length === 0 && <div className="hist-empty">No history yet</div>}
      {items.map((item) => (
        <button
          key={item.query_id}
          className="hist-item"
          onClick={() =>
            onSelect(
              item.sql || item.question,
              item.sql ? "sql" : "natural_language",
            )
          }
        >
          <div className="hist-q">{item.question}</div>
          <div className="hist-meta">
            <span
              className="hist-status"
              style={{
                color:
                  item.status === "success"
                    ? "var(--green)"
                    : item.status === "blocked"
                      ? "var(--red)"
                      : "var(--yellow)",
              }}
            >
              {item.status}
            </span>
            {item.confidence && (
              <span className="hist-conf">
                {Math.round(item.confidence * 100)}%
              </span>
            )}
          </div>
        </button>
      ))}
    </div>
  );
}

// ─── Eval Panel ───────────────────────────────────────────────────────
/** @param {{config: import("./types").AppConfig | null}} props */
function EvalPanel({ config }) {
  const [result, setResult] = useState(
    /** @type {import("./types").EvalResult | null} */ (null),
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(/** @type {string | null} */ (null));

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await runEval();
      setResult(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="eval-panel">
      <h1>Evaluation suite</h1>
      <p className="eval-desc">
        Runs {config?.eval_cases ?? "the configured"} smoke cases against the
        live model. Checks column names and row counts, not semantic accuracy.
        Each run makes multiple provider calls and may incur charges.
      </p>
      <button
        className="run-eval-btn"
        onClick={run}
        disabled={loading || !config?.live_evals_enabled}
      >
        {loading ? (
          <>
            <Loader2 size={12} className="spin" /> Running evals…
          </>
        ) : (
          <>
            <BarChart2 size={12} /> Run Evals
          </>
        )}
      </button>
      {!config?.live_evals_enabled && (
        <p className="page-description">
          Live evaluations are disabled. Set ENABLE_LIVE_EVALS=true on the
          server to enable them. Deterministic regression tests run locally
          without API keys.
        </p>
      )}
      {error && (
        <div role="alert" className="eval-error">
          {error}
        </div>
      )}
      {result && (
        <div className="eval-results">
          <div className="eval-grid">
            {[
              { label: "Shape Pass Rate", value: result.shape_pass_rate },
              {
                label: "Guardrail Effectiveness",
                value: result.guardrail_effectiveness,
              },
              { label: "Flagged Case Rate", value: result.flagged_case_rate },
              { label: "Avg Confidence", value: result.average_confidence },
            ].map((m) => (
              <div key={m.label} className="eval-metric">
                <div
                  className="eval-metric-val"
                  style={{
                    color:
                      m.value >= 0.8
                        ? "var(--green)"
                        : m.value >= 0.5
                          ? "var(--yellow)"
                          : "var(--red)",
                  }}
                >
                  {Math.round(m.value * 100)}%
                </div>
                <div className="eval-metric-label">{m.label}</div>
              </div>
            ))}
          </div>
          <div className="eval-case-list">
            {result.details.map((d, i) => (
              <div
                key={i}
                className={`eval-case ${d.passed ? "pass" : "fail"}`}
              >
                <span className="eval-case-icon">{d.passed ? "✓" : "✗"}</span>
                <span className="eval-case-q">{d.question}</span>
                {d.notes && (
                  <span className="eval-case-note">{d.notes[0]}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Sample Questions ─────────────────────────────────────────────────
const SAMPLES = [
  "What are the top 5 best-selling products by revenue?",
  "Show me monthly revenue for 2024",
  "Which customers have never placed an order?",
  "What is the return rate by reason?",
  "Which marketing campaign had the highest ROI?",
  "DELETE FROM customers WHERE is_active = false",
];

const SQL_SAMPLES = [
  {
    label: "Top products by revenue",
    sql: "SELECT name, category, revenue, units_sold FROM product_performance ORDER BY revenue DESC NULLS LAST LIMIT 5",
  },
  {
    label: "Monthly revenue",
    sql: "SELECT month, gross_revenue, orders FROM revenue_by_month ORDER BY month",
  },
  {
    label: "Customers by country",
    sql: "SELECT country, COUNT(*) AS customers FROM customers GROUP BY country ORDER BY customers DESC",
  },
  {
    label: "Browse the product catalog",
    sql: "SELECT name, category, unit_price, stock_quantity FROM products ORDER BY name",
  },
  {
    label: "Test a blocked write",
    sql: "DELETE FROM customers WHERE is_active = false",
  },
];

function SchemaPanel() {
  const [schema, setSchema] = useState(
    /** @type {import("./types").Schema | null} */ (null),
  );
  const [error, setError] = useState(/** @type {string | null} */ (null));
  useEffect(() => {
    getSchema()
      .then(setSchema)
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Request failed"),
      );
  }, []);
  return (
    <section className="schema-panel">
      <h1>Database schema</h1>
      <p className="page-description">
        Live PostgreSQL metadata. Explore tables, views and relationships before
        writing a query.
      </p>
      {error && (
        <p role="alert" className="eval-error">
          {error}
        </p>
      )}
      {!schema && !error && <p role="status">Loading schema…</p>}
      <div className="schema-grid">
        {schema?.tables.map((table) => (
          <article className="schema-card" key={table.name}>
            <h2>
              <Database size={16} /> {table.name}
            </h2>
            {table.comment && <p>{table.comment}</p>}
            <dl>
              {table.columns.map((col) => (
                <div key={col.name}>
                  <dt>
                    {col.name}
                    {table.primary_keys.includes(col.name) && (
                      <small> PK</small>
                    )}
                  </dt>
                  <dd>{col.type.toLowerCase()}</dd>
                </div>
              ))}
            </dl>
            {table.foreign_keys.map((key) => (
              <p className="schema-fk" key={key.column}>
                {key.column} → {key.references_table}.{key.references_column}
              </p>
            ))}
          </article>
        ))}
      </div>
    </section>
  );
}

export default function App() {
  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState(
    /** @type {import('./types').Mode} */ ("natural_language"),
  );
  const [results, setResults] = useState(
    /** @type {import("./types").QueryResult[]} */ ([]),
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(/** @type {string | null} */ (null));
  const [tab, setTab] = useState("query");
  const [config, setConfig] = useState(
    /** @type {import("./types").AppConfig | null} */ (null),
  );
  const [dbReady, setDbReady] = useState(/** @type {boolean | null} */ (null));
  const textareaRef = useRef(/** @type {HTMLTextAreaElement | null} */ (null));
  const resultRef = useRef(/** @type {HTMLDivElement | null} */ (null));
  const submitting = useRef(false);

  useEffect(() => {
    getConfig()
      .then(setConfig)
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Request failed"),
      );
    getReady()
      .then(() => setDbReady(true))
      .catch(() => setDbReady(false));
  }, []);

  /** @param {string} [q] @param {string | null} [clarification] */
  const submit = async (q = question, clarification = null) => {
    if (q.trim().length < 3 || submitting.current) return;
    submitting.current = true;
    setLoading(true);
    setError(null);
    try {
      const result = await queryNL(
        q.trim(),
        clarification ? "natural_language" : mode,
        clarification,
      );
      setResults((prev) => [result, ...prev].slice(0, 20));
      setQuestion("");
      requestAnimationFrame(() =>
        resultRef.current?.scrollTo({ top: 0, behavior: "smooth" }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      submitting.current = false;
      setLoading(false);
    }
  };
  /** @param {string} q @param {import("./types").Mode} [nextMode] */
  const selectSample = (q, nextMode = mode) => {
    setQuestion(q);
    setMode(nextMode);
    setTab("query");
    setTimeout(() => textareaRef.current?.focus(), 50);
  };

  return (
    <div className="app">
      <header className="app-header">
        <a
          className="logo"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setTab("query");
          }}
        >
          <Terminal size={22} />
          <span>QueryLens</span>
        </a>
        <span className="header-sub">A clearer view of your data</span>
        <div
          className={`connection-status ${dbReady ? "connected" : ""}`}
          role="status"
        >
          <span className="status-dot" />
          {dbReady === null
            ? "Connecting…"
            : dbReady
              ? "PostgreSQL connected"
              : "Database unavailable"}
        </div>
      </header>
      <div className="app-body">
        <aside className="sidebar">
          <div className="workspace-label">ANALYTICS WORKSPACE</div>
          <nav className="sidebar-nav" aria-label="Main navigation">
            {[
              { id: "query", label: "Query workspace", icon: Terminal },
              { id: "schema", label: "Database schema", icon: Database },
              { id: "history", label: "Query history", icon: RotateCcw },
              { id: "eval", label: "Evaluations", icon: BarChart2 },
            ].map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                className={`nav-btn ${tab === id ? "active" : ""}`}
                aria-current={tab === id ? "page" : undefined}
                onClick={() => setTab(id)}
              >
                <Icon size={17} />
                {label}
              </button>
            ))}
          </nav>
          <div className="sidebar-note">
            <Shield size={18} />
            <strong>Read-only by design</strong>
            <p>
              Queries pass SQL policy checks and run in a read-only transaction.
            </p>
            <span>Up to {config?.max_rows ?? 1000} rows per query</span>
          </div>
        </aside>
        <main className="main-content">
          {tab === "history" && (
            <div className="page-content">
              <HistoryPanel onSelect={selectSample} />
            </div>
          )}
          {tab === "eval" && (
            <div className="page-content">
              <EvalPanel config={config} />
            </div>
          )}
          {tab === "schema" && (
            <div className="page-content">
              <SchemaPanel />
            </div>
          )}
          {tab === "query" && (
            <>
              <div className="workspace-heading">
                <div>
                  <span className="eyebrow">EXPLORE & VERIFY</span>
                  <h1>Query your data</h1>
                  <p>Inspect the SQL. Explore the results. Keep the context.</p>
                </div>
                <span className="workspace-chip">
                  <Database size={14} /> PostgreSQL
                </span>
              </div>
              <div className="results-area" ref={resultRef} aria-live="polite">
                {results.length === 0 && (
                  <section className="empty-state">
                    <div className="empty-title">Start with a question</div>
                    <p className="empty-sub">
                      Use AI to translate plain English, or run a read-only SQL
                      query directly. Every result shows the SQL that actually
                      ran.
                    </p>
                    <div className="sample-queries">
                      <h2>
                        {mode === "sql"
                          ? "Explore the sample database"
                          : "Questions to get started"}
                      </h2>
                      {(mode === "sql"
                        ? SQL_SAMPLES
                        : SAMPLES.slice(0, 5).map((q) => ({ label: q, sql: q }))
                      ).map((sample) => (
                        <button
                          key={sample.label}
                          className="sample-btn"
                          onClick={() => selectSample(sample.sql)}
                        >
                          <span>{sample.label}</span>
                          <ChevronRight size={16} />
                        </button>
                      ))}
                    </div>
                  </section>
                )}
                {results.map((r) => (
                  <ResultCard
                    key={r.query_id}
                    result={r}
                    onClarify={submit}
                    busy={loading}
                  />
                ))}
                {loading && (
                  <p role="status" className="loading-state">
                    <Loader2 className="spin" size={18} />
                    {mode === "sql"
                      ? "Validating and executing SQL…"
                      : "Generating SQL and checking the results…"}
                  </p>
                )}
              </div>
              <div className="input-section">
                <div className="mode-row">
                  <div
                    className="mode-switch"
                    role="group"
                    aria-label="Query mode"
                  >
                    <button
                      aria-pressed={mode === "natural_language"}
                      disabled={loading}
                      onClick={() => setMode("natural_language")}
                    >
                      Ask AI
                    </button>
                    <button
                      aria-pressed={mode === "sql"}
                      disabled={loading}
                      onClick={() => setMode("sql")}
                    >
                      SQL
                    </button>
                  </div>
                  <span>
                    {mode === "sql"
                      ? "Direct execution · No model calls"
                      : "Uses your configured provider · Usage charges may apply"}
                  </span>
                </div>
                {mode === "natural_language" &&
                  config &&
                  !config.ai_configured && (
                    <p className="config-note">
                      AI needs a provider key and model ID. Use SQL mode to
                      explore the database.
                    </p>
                  )}
                <div className="input-wrap">
                  <label className="sr-only" htmlFor="query-input">
                    {mode === "sql" ? "SQL query" : "Your question"}
                  </label>
                  <textarea
                    id="query-input"
                    ref={textareaRef}
                    className="query-input"
                    value={question}
                    maxLength={2000}
                    onChange={(e) => setQuestion(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                        e.preventDefault();
                        submit();
                      }
                    }}
                    placeholder={
                      mode === "sql"
                        ? "SELECT name, category, unit_price FROM products LIMIT 10"
                        : "Which products generated the most revenue?"
                    }
                    rows={3}
                    disabled={loading}
                  />
                  <div className="input-footer">
                    <span className="input-hint">Ctrl / ⌘ + Enter to run</span>
                    <button
                      className="run-btn"
                      onClick={() => submit()}
                      disabled={loading || question.trim().length < 3}
                    >
                      {loading ? (
                        <>
                          <Loader2 size={16} className="spin" />
                          Running…
                        </>
                      ) : (
                        <>
                          <Zap size={16} />
                          Run query
                        </>
                      )}
                    </button>
                  </div>
                </div>
                {error && (
                  <p role="alert" className="global-error">
                    <XCircle size={16} />
                    {error}
                  </p>
                )}
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  );
}
