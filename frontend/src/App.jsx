import { useState, useRef, useEffect, useCallback } from 'react'
import {
  Terminal, Shield, AlertTriangle, CheckCircle2,
  XCircle, Clock, Database, ChevronRight, RotateCcw,
  ThumbsUp, ThumbsDown, BarChart2, Loader2, Info,
  ChevronDown, ChevronUp, Layers, Zap
} from 'lucide-react'
import { queryNL, sendFeedback, getHistory, runEval } from './lib/api.js'

// ─── Syntax Highlighter ───────────────────────────────────────────────
function SqlHighlight({ sql }) {
  if (!sql) return null
  const keywords = /\b(SELECT|FROM|WHERE|JOIN|LEFT|RIGHT|INNER|OUTER|GROUP BY|ORDER BY|HAVING|LIMIT|AND|OR|NOT|IN|EXISTS|UNION|AS|ON|DISTINCT|COUNT|SUM|AVG|MAX|MIN|CASE|WHEN|THEN|ELSE|END|WITH|OVER|PARTITION|BY|NULL|IS|LIKE|BETWEEN|DATE_TRUNC|EXTRACT|COALESCE|NULLIF|ROUND)\b/gi
  const strings = /'[^']*'/g
  const numbers = /\b\d+(\.\d+)?\b/g

  let html = sql
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  html = html.replace(keywords, m => `<span class="kw">${m.toUpperCase()}</span>`)
  html = html.replace(strings, m => `<span class="str">${m}</span>`)
  html = html.replace(numbers, m => `<span class="num">${m}</span>`)

  return (
    <pre
      className="sql-block"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}

// ─── Confidence Ring ───────────────────────────────────────────────────
function ConfidenceRing({ score }) {
  const pct = Math.round(score * 100)
  const r = 22, circ = 2 * Math.PI * r
  const dash = (score * circ).toFixed(1)
  const color = score >= 0.8 ? 'var(--green)' : score >= 0.55 ? 'var(--yellow)' : 'var(--red)'

  return (
    <div className="conf-ring" title={`Confidence: ${pct}%`}>
      <svg width="64" height="64" viewBox="0 0 64 64">
        <circle cx="32" cy="32" r={r} fill="none" stroke="var(--bg-4)" strokeWidth="4" />
        <circle
          cx="32" cy="32" r={r} fill="none"
          stroke={color} strokeWidth="4"
          strokeDasharray={`${dash} ${circ}`}
          strokeLinecap="round"
          transform="rotate(-90 32 32)"
          style={{ transition: 'stroke-dasharray 0.6s ease' }}
        />
      </svg>
      <span className="conf-pct" style={{ color }}>{pct}%</span>
    </div>
  )
}

// ─── Confidence Breakdown ──────────────────────────────────────────────
function ConfidenceBreakdown({ confidence }) {
  if (!confidence) return null
  const metrics = [
    { label: 'Syntax Valid', value: confidence.syntax_valid },
    { label: 'Back-Translation', value: confidence.back_translation_alignment },
    { label: 'Result Sanity', value: confidence.result_sanity },
    { label: 'Schema Coverage', value: confidence.schema_coverage },
  ]
  return (
    <div className="conf-breakdown">
      {metrics.map(m => (
        <div key={m.label} className="conf-metric">
          <span className="conf-metric-label">{m.label}</span>
          <div className="conf-bar-track">
            <div
              className="conf-bar-fill"
              style={{
                width: `${m.value * 100}%`,
                background: m.value >= 0.8 ? 'var(--green)' : m.value >= 0.55 ? 'var(--yellow)' : 'var(--red)',
              }}
            />
          </div>
          <span className="conf-metric-val">{Math.round(m.value * 100)}%</span>
        </div>
      ))}
    </div>
  )
}

// ─── Data Table ───────────────────────────────────────────────────────
function ResultTable({ columns, rows, totalRows }) {
  const [sortCol, setSortCol] = useState(null)
  const [sortDir, setSortDir] = useState('asc')
  const [page, setPage] = useState(0)
  const PAGE = 20

  const toggleSort = (col) => {
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortCol(col); setSortDir('asc') }
    setPage(0)
  }

  let sorted = [...rows]
  if (sortCol !== null) {
    const idx = sortCol
    sorted.sort((a, b) => {
      const va = a[idx], vb = b[idx]
      if (va === null) return 1
      if (vb === null) return -1
      const numA = parseFloat(va), numB = parseFloat(vb)
      const comp = !isNaN(numA) && !isNaN(numB)
        ? numA - numB
        : String(va).localeCompare(String(vb))
      return sortDir === 'asc' ? comp : -comp
    })
  }

  const pageRows = sorted.slice(page * PAGE, (page + 1) * PAGE)
  const totalPages = Math.ceil(sorted.length / PAGE)

  return (
    <div className="result-table-wrap">
      <div className="table-scroll">
        <table className="result-table">
          <thead>
            <tr>
              {columns.map((col, i) => (
                <th key={col} onClick={() => toggleSort(i)} className="sortable-th">
                  <span>{col}</span>
                  {sortCol === i && (
                    sortDir === 'asc' ? <ChevronUp size={11} /> : <ChevronDown size={11} />
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageRows.map((row, ri) => (
              <tr key={ri}>
                {row.map((cell, ci) => (
                  <td key={ci} className={cell === null ? 'null-cell' : ''}>
                    {cell === null ? <span className="null-val">NULL</span> : String(cell)}
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
            <button disabled={page === 0} onClick={() => setPage(p => p - 1)}>←</button>
            <span>{page + 1} / {totalPages}</span>
            <button disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)}>→</button>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Query Result Card ────────────────────────────────────────────────
function ResultCard({ result, onFeedback }) {
  const [sqlOpen, setSqlOpen] = useState(true)
  const [detailOpen, setDetailOpen] = useState(false)
  const [feedbackGiven, setFeedbackGiven] = useState(null)

  const handleFeedback = async (correct) => {
    setFeedbackGiven(correct)
    await sendFeedback(result.query_id, correct)
  }

  const statusColor = {
    success: 'var(--green)',
    blocked: 'var(--red)',
    error: 'var(--red)',
    clarification_needed: 'var(--yellow)',
  }[result.status] || 'var(--text-dim)'

  const conf = result.confidence?.overall
  const confColor = !conf ? null : conf >= 0.8 ? 'var(--green)' : conf >= 0.55 ? 'var(--yellow)' : 'var(--red)'

  return (
    <div className="result-card">
      {/* Header */}
      <div className="result-header">
        <div className="result-question">
          <Terminal size={13} style={{ opacity: 0.5 }} />
          <span>{result.question}</span>
        </div>
        <div className="result-meta">
          <span className="status-badge" style={{ color: statusColor, borderColor: statusColor }}>
            {result.status.replace('_', ' ')}
          </span>
          {result.execution_time_ms && (
            <span className="meta-chip">
              <Clock size={10} /> {result.execution_time_ms}ms
            </span>
          )}
        </div>
      </div>

      {/* Blocked */}
      {result.status === 'blocked' && (
        <div className="alert-box red">
          <Shield size={14} />
          <div>
            <div className="alert-title">Query Blocked by Guardrails</div>
            {result.guardrail_violations.filter(v => v.severity === 'block').map((v, i) => (
              <div key={i} className="alert-item">⊘ [{v.rule}] {v.detail}</div>
            ))}
          </div>
        </div>
      )}

      {/* Clarification */}
      {result.status === 'clarification_needed' && (
        <div className="clarification-box">
          <div className="clar-title">
            <Info size={13} /> Ambiguous question — which did you mean?
          </div>
          {result.clarification_options.map((opt, i) => (
            <div key={i} className="clar-option">
              <div className="clar-label">{opt.label}</div>
              <div className="clar-desc">{opt.description}</div>
              <pre className="clar-sql">{opt.example_sql}</pre>
            </div>
          ))}
        </div>
      )}

      {/* Error */}
      {result.status === 'error' && (
        <div className="alert-box red">
          <XCircle size={14} />
          <div>{result.error_message}</div>
        </div>
      )}

      {/* Success */}
      {result.status === 'success' && (
        <>
          {/* Guardrail warnings */}
          {result.guardrail_violations.filter(v => v.severity === 'warn').map((v, i) => (
            <div key={i} className="alert-box yellow">
              <AlertTriangle size={12} />
              <span>[{v.rule}] {v.detail}</span>
            </div>
          ))}

          {/* Hallucination flags */}
          {result.hallucination_flags.length > 0 && (
            <div className="alert-box yellow">
              <AlertTriangle size={13} />
              <div>
                <div className="alert-title">Hallucination Detector Flags</div>
                {result.hallucination_flags.map((f, i) => (
                  <div key={i} className="alert-item">⚠ {f}</div>
                ))}
              </div>
            </div>
          )}

          {/* SQL + Confidence row */}
          <div className="sql-conf-row">
            <div className="sql-section">
              <button
                className="section-toggle"
                onClick={() => setSqlOpen(o => !o)}
              >
                <Database size={11} />
                Generated SQL
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
                  {conf >= 0.8 ? 'High Confidence' : conf >= 0.55 ? 'Medium Confidence' : 'Low Confidence'}
                </div>
              </div>
            )}
          </div>

          {/* Breakdown toggle */}
          {result.confidence && (
            <button
              className="detail-toggle"
              onClick={() => setDetailOpen(o => !o)}
            >
              <Layers size={10} />
              {detailOpen ? 'Hide' : 'Show'} confidence breakdown
            </button>
          )}
          {detailOpen && <ConfidenceBreakdown confidence={result.confidence} />}

          {/* Tables used */}
          {result.tables_used?.length > 0 && (
            <div className="tables-used">
              <Zap size={10} />
              {result.tables_used.map(t => (
                <span key={t} className="table-chip">{t}</span>
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
            <span className="feedback-label">Was this result correct?</span>
            {feedbackGiven === null ? (
              <>
                <button className="fb-btn green" onClick={() => handleFeedback(true)}>
                  <ThumbsUp size={11} /> Yes
                </button>
                <button className="fb-btn red" onClick={() => handleFeedback(false)}>
                  <ThumbsDown size={11} /> No
                </button>
              </>
            ) : (
              <span className="fb-thanks">
                {feedbackGiven ? <CheckCircle2 size={12} color="var(--green)" /> : <XCircle size={12} color="var(--red)" />}
                Feedback recorded
              </span>
            )}
          </div>
        </>
      )}
    </div>
  )
}

// ─── History Panel ────────────────────────────────────────────────────
function HistoryPanel({ onSelect }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getHistory(20).then(setItems).catch(() => {}).finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="hist-loading"><Loader2 size={14} className="spin" /></div>

  return (
    <div className="history-panel">
      <div className="panel-title">Recent Queries</div>
      {items.length === 0 && <div className="hist-empty">No history yet</div>}
      {items.map(item => (
        <button
          key={item.query_id}
          className="hist-item"
          onClick={() => onSelect(item.question)}
        >
          <div className="hist-q">{item.question}</div>
          <div className="hist-meta">
            <span
              className="hist-status"
              style={{
                color: item.status === 'success' ? 'var(--green)' :
                       item.status === 'blocked' ? 'var(--red)' : 'var(--yellow)'
              }}
            >
              {item.status}
            </span>
            {item.confidence && (
              <span className="hist-conf">{Math.round(item.confidence * 100)}%</span>
            )}
          </div>
        </button>
      ))}
    </div>
  )
}

// ─── Eval Panel ───────────────────────────────────────────────────────
function EvalPanel() {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const run = async () => {
    setLoading(true)
    setError(null)
    try {
      const r = await runEval()
      setResult(r)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="eval-panel">
      <div className="panel-title">Evaluation Suite</div>
      <p className="eval-desc">
        Runs {30}+ golden test cases measuring execution accuracy, hallucination detection, and guardrail effectiveness.
      </p>
      <button className="run-eval-btn" onClick={run} disabled={loading}>
        {loading ? <><Loader2 size={12} className="spin" /> Running evals…</> : <><BarChart2 size={12} /> Run Evals</>}
      </button>
      {error && <div className="eval-error">{error}</div>}
      {result && (
        <div className="eval-results">
          <div className="eval-grid">
            {[
              { label: 'Execution Accuracy', value: result.execution_accuracy },
              { label: 'Guardrail Effectiveness', value: result.guardrail_effectiveness },
              { label: 'Hallucination Detection', value: result.hallucination_detection_rate },
              { label: 'Avg Confidence', value: result.average_confidence },
            ].map(m => (
              <div key={m.label} className="eval-metric">
                <div
                  className="eval-metric-val"
                  style={{ color: m.value >= 0.8 ? 'var(--green)' : m.value >= 0.5 ? 'var(--yellow)' : 'var(--red)' }}
                >
                  {Math.round(m.value * 100)}%
                </div>
                <div className="eval-metric-label">{m.label}</div>
              </div>
            ))}
          </div>
          <div className="eval-case-list">
            {result.details.map((d, i) => (
              <div key={i} className={`eval-case ${d.passed ? 'pass' : 'fail'}`}>
                <span className="eval-case-icon">{d.passed ? '✓' : '✗'}</span>
                <span className="eval-case-q">{d.question}</span>
                {d.notes && <span className="eval-case-note">{d.notes[0]}</span>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Sample Questions ─────────────────────────────────────────────────
const SAMPLES = [
  "What are the top 5 best-selling products by revenue?",
  "Show me monthly revenue for 2024",
  "Which customers have never placed an order?",
  "What is the return rate by reason?",
  "Which marketing campaign had the highest ROI?",
  "DELETE FROM customers WHERE is_active = false",
]

// ─── Main App ─────────────────────────────────────────────────────────
export default function App() {
  const [question, setQuestion] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [tab, setTab] = useState('query') // 'query' | 'history' | 'eval'
  const textareaRef = useRef(null)
  const resultsEndRef = useRef(null)

  const submit = useCallback(async (q = question) => {
    if (!q.trim() || loading) return
    setLoading(true)
    setError(null)
    try {
      const result = await queryNL(q.trim())
      setResults(prev => [result, ...prev])
      setQuestion('')
      setTimeout(() => resultsEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 100)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [question, loading])

  const handleKey = (e) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submit()
  }

  const selectSample = (q) => {
    setQuestion(q)
    setTab('query')
    setTimeout(() => textareaRef.current?.focus(), 50)
  }

  return (
    <div className="app">
      {/* Header */}
      <header className="app-header">
        <div className="header-left">
          <div className="logo">
            <Terminal size={16} />
            <span>QueryLens</span>
          </div>
          <div className="header-sub">Text-to-SQL · Guardrails · Hallucination Detection</div>
        </div>
        <div className="header-right">
          <div className="header-badges">
            <span className="hbadge green"><Shield size={9} /> Guardrails Active</span>
            <span className="hbadge cyan"><CheckCircle2 size={9} /> Hallucination Detector</span>
            <span className="hbadge accent"><Database size={9} /> PostgreSQL</span>
          </div>
        </div>
      </header>

      <div className="app-body">
        {/* Sidebar */}
        <aside className="sidebar">
          <nav className="sidebar-nav">
            {[
              { id: 'query', label: 'Query', icon: Terminal },
              { id: 'history', label: 'History', icon: RotateCcw },
              { id: 'eval', label: 'Evals', icon: BarChart2 },
            ].map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                className={`nav-btn ${tab === id ? 'active' : ''}`}
                onClick={() => setTab(id)}
              >
                <Icon size={13} />
                {label}
              </button>
            ))}
          </nav>

          {tab === 'query' && (
            <div className="sample-queries">
              <div className="panel-title">Sample Queries</div>
              {SAMPLES.map((s, i) => (
                <button key={i} className="sample-btn" onClick={() => selectSample(s)}>
                  <ChevronRight size={10} />
                  <span>{s}</span>
                </button>
              ))}
            </div>
          )}
          {tab === 'history' && <HistoryPanel onSelect={selectSample} />}
          {tab === 'eval' && <EvalPanel />}
        </aside>

        {/* Main content */}
        <main className="main-content">
          {/* Results */}
          <div className="results-area">
            {results.length === 0 && !loading && (
              <div className="empty-state">
                <Terminal size={32} style={{ opacity: 0.15, marginBottom: 12 }} />
                <div className="empty-title">Ready to translate</div>
                <div className="empty-sub">
                  Ask a question in plain English. SQL is generated, sandboxed, and validated automatically.
                </div>
                <div className="feature-grid">
                  {[
                    { icon: Shield, label: 'Guardrails', desc: 'DDL/DML blocked' },
                    { icon: AlertTriangle, label: 'Hallucination Detection', desc: 'Back-translation + sanity' },
                    { icon: BarChart2, label: 'Confidence Score', desc: '4-signal weighted metric' },
                    { icon: Database, label: 'Read-only Sandbox', desc: 'Auto-rollback transactions' },
                  ].map(({ icon: Icon, label, desc }) => (
                    <div key={label} className="feature-card">
                      <Icon size={16} />
                      <div className="feature-label">{label}</div>
                      <div className="feature-desc">{desc}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {results.map((r, i) => (
              <ResultCard key={r.query_id || i} result={r} />
            ))}
            <div ref={resultsEndRef} />
          </div>

          {/* Input area */}
          <div className="input-section">
            <div className="input-wrap">
              <textarea
                ref={textareaRef}
                className="query-input"
                value={question}
                onChange={e => setQuestion(e.target.value)}
                onKeyDown={handleKey}
                placeholder="Ask anything about your data… e.g. &quot;What are the top 5 products by revenue?&quot;"
                rows={3}
                disabled={loading}
              />
              <div className="input-footer">
                <span className="input-hint">⌘+Enter to run</span>
                <button
                  className="run-btn"
                  onClick={() => submit()}
                  disabled={loading || !question.trim()}
                >
                  {loading ? (
                    <><Loader2 size={13} className="spin" /> Translating…</>
                  ) : (
                    <><Zap size={13} /> Run Query</>
                  )}
                </button>
              </div>
            </div>
            {error && (
              <div className="global-error">
                <XCircle size={13} /> {error}
              </div>
            )}
          </div>
        </main>
      </div>

      <style>{`
        /* ── Layout ── */
        .app { display: flex; flex-direction: column; height: 100vh; overflow: hidden; }
        .app-header {
          display: flex; align-items: center; justify-content: space-between;
          padding: 12px 20px; border-bottom: 1px solid var(--border);
          background: var(--bg-2); flex-shrink: 0; gap: 16px;
        }
        .header-left { display: flex; align-items: baseline; gap: 16px; }
        .logo {
          display: flex; align-items: center; gap: 7px;
          font-family: var(--font-display); font-size: 1.1rem; font-weight: 700;
          color: var(--accent); letter-spacing: -0.02em;
        }
        .header-sub { font-size: 0.72rem; color: var(--text-dim); }
        .header-right { display: flex; align-items: center; }
        .header-badges { display: flex; gap: 8px; flex-wrap: wrap; }
        .hbadge {
          display: flex; align-items: center; gap: 4px;
          font-size: 0.65rem; padding: 3px 8px; border-radius: 100px;
          border: 1px solid currentColor; opacity: 0.7;
        }
        .hbadge.green { color: var(--green); }
        .hbadge.cyan { color: var(--cyan); }
        .hbadge.accent { color: var(--accent); }

        .app-body { display: flex; flex: 1; overflow: hidden; }

        /* ── Sidebar ── */
        .sidebar {
          width: 240px; flex-shrink: 0; border-right: 1px solid var(--border);
          background: var(--bg-2); display: flex; flex-direction: column;
          overflow-y: auto; overflow-x: hidden;
        }
        .sidebar-nav { display: flex; flex-direction: column; padding: 12px 8px; gap: 2px; }
        .nav-btn {
          display: flex; align-items: center; gap: 8px;
          padding: 7px 10px; border-radius: var(--radius);
          background: none; border: none; color: var(--text-dim);
          cursor: pointer; font-family: var(--font-mono); font-size: 0.78rem;
          transition: all 0.15s; text-align: left;
        }
        .nav-btn:hover { background: var(--bg-4); color: var(--text); }
        .nav-btn.active { background: var(--accent-dim); color: var(--accent); }
        .panel-title {
          font-size: 0.65rem; font-weight: 600; color: var(--text-muted);
          text-transform: uppercase; letter-spacing: 0.1em;
          padding: 12px 12px 6px;
        }
        .sample-queries { display: flex; flex-direction: column; }
        .sample-btn {
          display: flex; align-items: flex-start; gap: 6px;
          padding: 7px 12px; background: none; border: none;
          color: var(--text-dim); cursor: pointer; font-family: var(--font-mono);
          font-size: 0.72rem; text-align: left; line-height: 1.4;
          transition: all 0.12s; border-left: 2px solid transparent;
        }
        .sample-btn:hover {
          color: var(--text); background: var(--bg-3);
          border-left-color: var(--accent);
        }
        .sample-btn svg { margin-top: 3px; flex-shrink: 0; }

        /* ── Main ── */
        .main-content {
          flex: 1; display: flex; flex-direction: column;
          overflow: hidden; background: var(--bg);
        }
        .input-section {
          flex-shrink: 0; padding: 16px 20px;
          border-top: 1px solid var(--border); background: var(--bg-2);
        }
        .input-wrap {
          border: 1px solid var(--border-bright); border-radius: var(--radius-lg);
          overflow: hidden; background: var(--bg-3);
          transition: border-color 0.2s;
        }
        .input-wrap:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-glow); }
        .query-input {
          width: 100%; padding: 12px 14px; background: transparent;
          border: none; outline: none; color: var(--text);
          font-family: var(--font-mono); font-size: 0.85rem; resize: none;
          line-height: 1.6;
        }
        .query-input::placeholder { color: var(--text-muted); }
        .query-input:disabled { opacity: 0.6; }
        .input-footer {
          display: flex; align-items: center; justify-content: space-between;
          padding: 8px 12px; border-top: 1px solid var(--border);
        }
        .input-hint { font-size: 0.65rem; color: var(--text-muted); }
        .run-btn {
          display: flex; align-items: center; gap: 6px;
          padding: 6px 14px; background: var(--accent); border: none;
          border-radius: var(--radius); color: #fff; cursor: pointer;
          font-family: var(--font-mono); font-size: 0.78rem; font-weight: 500;
          transition: all 0.15s;
        }
        .run-btn:hover:not(:disabled) { background: #6a58e0; transform: translateY(-1px); }
        .run-btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .global-error {
          display: flex; align-items: center; gap: 6px;
          margin-top: 8px; padding: 8px 12px;
          background: var(--red-dim); border: 1px solid var(--red);
          border-radius: var(--radius); color: var(--red); font-size: 0.78rem;
        }

        /* ── Results ── */
        .results-area {
          flex: 1; overflow-y: auto; padding: 16px 20px;
          display: flex; flex-direction: column; gap: 16px;
        }
        .empty-state {
          flex: 1; display: flex; flex-direction: column;
          align-items: center; justify-content: center;
          text-align: center; padding: 48px 24px; min-height: 400px;
        }
        .empty-title {
          font-family: var(--font-display); font-size: 1.2rem; font-weight: 700;
          color: var(--text); margin-bottom: 8px;
        }
        .empty-sub { font-size: 0.78rem; color: var(--text-dim); max-width: 380px; margin-bottom: 32px; }
        .feature-grid {
          display: grid; grid-template-columns: 1fr 1fr; gap: 12px; max-width: 480px;
        }
        .feature-card {
          padding: 14px 16px; background: var(--bg-3);
          border: 1px solid var(--border); border-radius: var(--radius-lg);
          text-align: left;
        }
        .feature-card svg { color: var(--accent); margin-bottom: 6px; }
        .feature-label { font-size: 0.78rem; font-weight: 600; color: var(--text); }
        .feature-desc { font-size: 0.7rem; color: var(--text-dim); }

        /* ── Result Card ── */
        .result-card {
          background: var(--bg-2); border: 1px solid var(--border);
          border-radius: var(--radius-lg); overflow: hidden;
          animation: slideIn 0.2s ease;
        }
        @keyframes slideIn {
          from { opacity: 0; transform: translateY(8px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .result-header {
          display: flex; align-items: flex-start; justify-content: space-between;
          gap: 12px; padding: 12px 14px;
          border-bottom: 1px solid var(--border); background: var(--bg-3);
        }
        .result-question {
          display: flex; align-items: flex-start; gap: 8px;
          font-size: 0.82rem; color: var(--text); flex: 1;
        }
        .result-question svg { margin-top: 2px; flex-shrink: 0; }
        .result-meta { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
        .status-badge {
          font-size: 0.65rem; padding: 2px 7px;
          border: 1px solid; border-radius: 100px; text-transform: uppercase; letter-spacing: 0.05em;
        }
        .meta-chip {
          display: flex; align-items: center; gap: 3px;
          font-size: 0.65rem; color: var(--text-dim);
        }

        /* Alert boxes */
        .alert-box {
          display: flex; align-items: flex-start; gap: 10px;
          margin: 10px 14px; padding: 10px 12px;
          border-radius: var(--radius); font-size: 0.78rem;
          border: 1px solid;
        }
        .alert-box.red { background: var(--red-dim); border-color: var(--red); color: var(--red); }
        .alert-box.yellow { background: var(--yellow-dim); border-color: var(--yellow); color: var(--yellow); }
        .alert-title { font-weight: 600; margin-bottom: 4px; }
        .alert-item { margin-top: 3px; opacity: 0.9; }

        /* Clarification */
        .clarification-box { margin: 10px 14px; }
        .clar-title {
          display: flex; align-items: center; gap: 6px;
          font-size: 0.78rem; color: var(--yellow); margin-bottom: 8px;
        }
        .clar-option {
          padding: 10px 12px; margin-bottom: 8px;
          background: var(--bg-4); border: 1px solid var(--border-bright);
          border-radius: var(--radius);
        }
        .clar-label { font-size: 0.78rem; font-weight: 600; color: var(--text); }
        .clar-desc { font-size: 0.72rem; color: var(--text-dim); margin-top: 2px; }
        .clar-sql {
          margin-top: 6px; font-size: 0.68rem; color: var(--cyan);
          background: var(--bg); padding: 6px 8px; border-radius: 4px;
          overflow-x: auto; white-space: pre-wrap; word-break: break-all;
        }

        /* SQL section */
        .sql-conf-row {
          display: flex; align-items: flex-start; gap: 0;
          margin: 10px 14px 0; flex-wrap: wrap;
        }
        .sql-section { flex: 1; min-width: 0; }
        .section-toggle {
          display: flex; align-items: center; gap: 5px;
          background: none; border: none; color: var(--text-dim);
          cursor: pointer; font-family: var(--font-mono); font-size: 0.72rem;
          padding: 0; margin-bottom: 6px; transition: color 0.12s;
        }
        .section-toggle:hover { color: var(--text); }

        .sql-block {
          background: var(--bg); border: 1px solid var(--border);
          border-radius: var(--radius); padding: 10px 12px;
          font-family: var(--font-mono); font-size: 0.78rem; line-height: 1.7;
          overflow-x: auto; white-space: pre-wrap; word-break: break-word;
          color: var(--text);
        }
        .sql-block .kw { color: var(--accent); font-weight: 600; }
        .sql-block .str { color: var(--green); }
        .sql-block .num { color: var(--yellow); }

        .explanation {
          margin-top: 6px; font-size: 0.75rem; color: var(--text-dim);
          font-style: italic; line-height: 1.5;
        }

        .confidence-section {
          display: flex; flex-direction: column; align-items: center;
          padding: 0 0 0 20px; gap: 4px; flex-shrink: 0;
        }
        .conf-ring { position: relative; width: 64px; height: 64px; display: flex; align-items: center; justify-content: center; }
        .conf-ring svg { position: absolute; top: 0; left: 0; }
        .conf-pct { font-size: 0.78rem; font-weight: 700; font-family: var(--font-display); z-index: 1; }
        .conf-label { font-size: 0.65rem; color: var(--text-dim); }

        .detail-toggle {
          display: flex; align-items: center; gap: 5px;
          background: none; border: none; color: var(--text-muted);
          cursor: pointer; font-family: var(--font-mono); font-size: 0.68rem;
          padding: 4px 14px; transition: color 0.12s;
        }
        .detail-toggle:hover { color: var(--text-dim); }

        .conf-breakdown { padding: 8px 14px; display: flex; flex-direction: column; gap: 6px; }
        .conf-metric { display: flex; align-items: center; gap: 10px; }
        .conf-metric-label { font-size: 0.7rem; color: var(--text-dim); width: 140px; flex-shrink: 0; }
        .conf-bar-track {
          flex: 1; height: 4px; background: var(--bg-4); border-radius: 2px; overflow: hidden;
        }
        .conf-bar-fill { height: 100%; border-radius: 2px; transition: width 0.5s ease; }
        .conf-metric-val { font-size: 0.7rem; color: var(--text-dim); width: 32px; text-align: right; }

        .tables-used {
          display: flex; align-items: center; gap: 6px;
          padding: 6px 14px; flex-wrap: wrap;
        }
        .tables-used svg { color: var(--text-muted); }
        .table-chip {
          font-size: 0.65rem; padding: 2px 7px;
          background: var(--bg-4); border: 1px solid var(--border-bright);
          border-radius: 100px; color: var(--cyan);
        }

        /* Result table */
        .result-table-wrap { margin: 10px 14px; }
        .table-scroll { overflow-x: auto; border: 1px solid var(--border); border-radius: var(--radius); }
        .result-table { width: 100%; border-collapse: collapse; font-size: 0.75rem; }
        .result-table th {
          padding: 7px 10px; text-align: left; background: var(--bg-4);
          border-bottom: 1px solid var(--border-bright); color: var(--text-dim);
          font-weight: 500; white-space: nowrap; position: sticky; top: 0;
        }
        .sortable-th {
          cursor: pointer; user-select: none;
          display: flex; align-items: center; gap: 4px;
        }
        .sortable-th:hover { color: var(--text); }
        .result-table td {
          padding: 6px 10px; border-bottom: 1px solid var(--border);
          color: var(--text); max-width: 280px;
          overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        }
        .result-table tr:last-child td { border-bottom: none; }
        .result-table tr:hover td { background: var(--bg-4); }
        .null-val { color: var(--text-muted); font-style: italic; }
        .table-footer {
          display: flex; align-items: center; justify-content: space-between;
          padding: 6px 10px; font-size: 0.68rem; color: var(--text-muted);
        }
        .table-count { }
        .pagination { display: flex; align-items: center; gap: 8px; }
        .pagination button {
          background: var(--bg-4); border: 1px solid var(--border);
          color: var(--text-dim); padding: 3px 8px; border-radius: 4px;
          cursor: pointer; font-family: var(--font-mono); font-size: 0.72rem;
        }
        .pagination button:disabled { opacity: 0.3; cursor: not-allowed; }
        .empty-result { padding: 16px 14px; font-size: 0.75rem; color: var(--text-muted); font-style: italic; }

        /* Feedback */
        .feedback-row {
          display: flex; align-items: center; gap: 8px;
          padding: 8px 14px 12px; border-top: 1px solid var(--border);
          margin-top: 6px;
        }
        .feedback-label { font-size: 0.68rem; color: var(--text-muted); }
        .fb-btn {
          display: flex; align-items: center; gap: 4px;
          padding: 4px 10px; border-radius: 4px; border: 1px solid;
          background: none; cursor: pointer; font-family: var(--font-mono);
          font-size: 0.68rem; transition: all 0.12s;
        }
        .fb-btn.green { color: var(--green); border-color: var(--green); }
        .fb-btn.green:hover { background: var(--green-dim); }
        .fb-btn.red { color: var(--red); border-color: var(--red); }
        .fb-btn.red:hover { background: var(--red-dim); }
        .fb-thanks { display: flex; align-items: center; gap: 5px; font-size: 0.7rem; color: var(--text-dim); }

        /* History panel */
        .hist-loading { display: flex; justify-content: center; padding: 20px; }
        .hist-empty { padding: 12px; font-size: 0.72rem; color: var(--text-muted); }
        .history-panel { display: flex; flex-direction: column; }
        .hist-item {
          padding: 9px 12px; background: none; border: none;
          border-left: 2px solid transparent; cursor: pointer;
          text-align: left; font-family: var(--font-mono);
          transition: all 0.12s; display: flex; flex-direction: column; gap: 3px;
        }
        .hist-item:hover { background: var(--bg-3); border-left-color: var(--accent); }
        .hist-q { font-size: 0.72rem; color: var(--text); line-height: 1.4; }
        .hist-meta { display: flex; align-items: center; gap: 8px; }
        .hist-status { font-size: 0.62rem; }
        .hist-conf { font-size: 0.62rem; color: var(--text-muted); }

        /* Eval panel */
        .eval-panel { padding: 0 12px 12px; display: flex; flex-direction: column; gap: 10px; }
        .eval-desc { font-size: 0.72rem; color: var(--text-dim); line-height: 1.5; }
        .run-eval-btn {
          display: flex; align-items: center; gap: 6px;
          padding: 8px 14px; background: var(--bg-4);
          border: 1px solid var(--border-bright); border-radius: var(--radius);
          color: var(--text); cursor: pointer; font-family: var(--font-mono);
          font-size: 0.75rem; transition: all 0.12s;
        }
        .run-eval-btn:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
        .run-eval-btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .eval-error { font-size: 0.72rem; color: var(--red); }
        .eval-results { display: flex; flex-direction: column; gap: 10px; }
        .eval-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
        .eval-metric {
          padding: 10px; background: var(--bg-4); border: 1px solid var(--border);
          border-radius: var(--radius); text-align: center;
        }
        .eval-metric-val { font-size: 1.3rem; font-weight: 800; font-family: var(--font-display); }
        .eval-metric-label { font-size: 0.62rem; color: var(--text-muted); margin-top: 2px; }
        .eval-case-list { display: flex; flex-direction: column; gap: 3px; max-height: 300px; overflow-y: auto; }
        .eval-case {
          display: flex; align-items: flex-start; gap: 6px;
          padding: 5px 8px; border-radius: 4px; font-size: 0.68rem;
        }
        .eval-case.pass { background: var(--green-dim); }
        .eval-case.fail { background: var(--red-dim); }
        .eval-case-icon { flex-shrink: 0; font-size: 0.7rem; }
        .eval-case.pass .eval-case-icon { color: var(--green); }
        .eval-case.fail .eval-case-icon { color: var(--red); }
        .eval-case-q { flex: 1; color: var(--text-dim); }
        .eval-case-note { font-size: 0.62rem; color: var(--text-muted); flex-shrink: 0; max-width: 100px; text-align: right; }

        /* Utilities */
        .spin { animation: spin 1s linear infinite; }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </div>
  )
}
