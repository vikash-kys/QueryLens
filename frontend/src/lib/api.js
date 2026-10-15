const BASE = '/v1'

export async function queryNL(question, sessionId = null) {
  const res = await fetch(`${BASE}/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, session_id: sessionId }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

export async function getSchema() {
  const res = await fetch(`${BASE}/schema`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function getHistory(limit = 20) {
  const res = await fetch(`${BASE}/history?limit=${limit}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function sendFeedback(queryId, isCorrect, comment = null) {
  const res = await fetch(`${BASE}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query_id: queryId, is_correct: isCorrect, comment }),
  })
  return res.json()
}

export async function runEval() {
  const res = await fetch(`${BASE}/eval`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}
