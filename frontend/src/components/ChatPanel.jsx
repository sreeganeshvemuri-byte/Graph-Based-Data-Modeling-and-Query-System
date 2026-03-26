import { useState, useRef, useEffect, useCallback } from 'react'
import './ChatPanel.css'

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
const API_STREAM = `${API_BASE}/query/stream`

const SUGGESTIONS = [
  'Show me the full journey for sales order 740509',
  'Which customer has the highest net value order?',
  'All orders containing product S8907367010814',
  'Which products have the highest number of billing documents?',
  'Find all data quality and broken flow issues',
  'Summarise this dataset',
]

function PlanBadge({ plan }) {
  const [open, setOpen] = useState(false)
  const intentColors = {
    trace_flow: '#6366f1',
    top_products_by_billing: '#0891b2',
    find_broken_flows: '#dc2626',
    lookup_entity: '#16a34a',
    sql_query: '#7c3aed',
    reject: '#94a3b8',
  }
  const label = plan.intent === 'sql_query' ? '⚡ sql query' : (plan.intent?.replace(/_/g, ' ') || '')
  return (
    <div className="plan-badge-wrap">
      <button className="plan-badge-btn" onClick={() => setOpen(o => !o)}
        style={{ borderColor: intentColors[plan.intent] || '#e2e8f0', color: intentColors[plan.intent] || '#94a3b8' }}>
        <span className="plan-badge-arrow" style={{ transform: open ? 'rotate(90deg)' : 'none' }}>▶</span>
        {label}
      </button>
      {open && (
        <div className="plan-detail">
          {plan.sql && <pre className="plan-sql">{plan.sql}</pre>}
          {!plan.sql && <pre className="plan-badge-json">{JSON.stringify(plan, null, 2)}</pre>}
        </div>
      )}
    </div>
  )
}

function StatPills({ result, plan }) {
  if (!result || plan?.intent === 'reject') return null
  const pills = []
  if (result.path?.nodes?.length > 0) pills.push({ label: `${result.path.nodes.length} nodes`, color: '#6366f1' })
  if (result.path?.edges?.length > 0) pills.push({ label: `${result.path.edges.length} edges`, color: '#0891b2' })
  if (result.results?.length > 0) pills.push({ label: `${result.results.length} products`, color: '#0d9488' })
  if (result.intent === 'find_broken_flows') {
    const n = result.issues?.length || 0
    pills.push({ label: n > 0 ? `${n} issues found` : 'No issues', color: n > 0 ? '#dc2626' : '#16a34a' })
  }
  if (result.intent === 'sql_query' || result.total_rows !== undefined || result.rows !== undefined) {
    const n = result.total_rows ?? result.row_count ?? result.rows?.length ?? 0
    pills.push({ label: `${n} row${n !== 1 ? 's' : ''}`, color: '#7c3aed' })
  }
  if (!pills.length) return null
  return (
    <div className="stat-pills">
      {pills.map(p => (
        <span key={p.label} className="stat-pill" style={{ color: p.color, borderColor: p.color + '30', background: p.color + '0a' }}>
          {p.label}
        </span>
      ))}
    </div>
  )
}

function ResultTable({ rows }) {
  if (!rows?.length) return null
  const keys = Object.keys(rows[0])
  return (
    <div className="result-table-wrap">
      <table className="result-table">
        <thead>
          <tr>{keys.map(k => <th key={k}>{k.replace(/_/g, ' ')}</th>)}</tr>
        </thead>
        <tbody>
          {rows.slice(0, 15).map((row, i) => (
            <tr key={i}>
              {keys.map(k => <td key={k}>{row[k] != null ? String(row[k]) : '—'}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > 15 && <p className="result-more">+{rows.length - 15} more rows</p>}
    </div>
  )
}

function IssueList({ issues }) {
  if (!issues?.length) return <p className="no-issues">✓ No issues detected</p>
  const byType = {}
  issues.forEach(i => { byType[i.break_type] = (byType[i.break_type] || 0) + 1 })
  return (
    <div className="issue-list">
      {Object.entries(byType).map(([type, count]) => (
        <div key={type} className="issue-row">
          <span className="issue-count">{count}</span>
          <span className="issue-type">{type.replace(/_/g, ' ')}</span>
        </div>
      ))}
    </div>
  )
}

function EntityCard({ result }) {
  if (!result?.entity) return null
  return (
    <div className="entity-card">
      <div className="entity-card-label">{result.entity_type?.replace(/_/g, ' ')} · {result.entity_id}</div>
      <div className="entity-fields">
        {Object.entries(result.entity)
          .filter(([, v]) => v != null && v !== '')
          .map(([k, v]) => (
            <div key={k} className="entity-field">
              <span className="entity-key">{k.replace(/([A-Z])/g, ' $1').trim()}</span>
              <span className="entity-val">{String(v)}</span>
            </div>
          ))}
      </div>
    </div>
  )
}

function Message({ msg }) {
  if (msg.role === 'user') {
    return (
      <div className="msg msg-user">
        <span className="msg-bubble-user">{msg.text}</span>
      </div>
    )
  }
  if (msg.role === 'error') {
    return (
      <div className="msg msg-error">
        <span className="msg-error-icon">⚠</span>
        <span className="msg-error-text">{msg.text}</span>
      </div>
    )
  }

  const { plan, result, nlAnswer, streaming } = msg

  return (
    <div className="msg msg-assistant">
      <div className="msg-avatar">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="10" fill="#1e293b"/>
          <path d="M8 12h8M12 8v8" stroke="white" strokeWidth="2" strokeLinecap="round"/>
        </svg>
      </div>
      <div className="msg-content">
        {plan && <PlanBadge plan={plan} />}
        <StatPills result={result} plan={plan} />
        {nlAnswer !== undefined && (
          <p className="msg-answer">
            {nlAnswer}
            {streaming && <span className="stream-cursor">▋</span>}
          </p>
        )}
        {result?.intent === 'top_products_by_billing' && <ResultTable rows={result.results} />}
        {result?.intent === 'find_broken_flows' && <IssueList issues={result.issues} />}
        {result?.intent === 'lookup_entity' && <EntityCard result={result} />}
        {(result?.intent === 'sql_query' || result?.queries !== undefined || result?.rows !== undefined) && (
          <SqlResultBlock result={result} />
        )}
      </div>
    </div>
  )
}

function SqlResultBlock({ result }) {
  // result has .queries: [{id, purpose, sql, rows, row_count, error}]
  // OR old shape: .rows, .sql
  const queries = result?.queries || (result?.rows !== undefined ? [{id:'q1', purpose:'', sql: result.sql, rows: result.rows, row_count: result.row_count ?? result.rows?.length, error: result.error}] : [])
  if (!queries.length) return null

  return (
    <div className="sql-result-wrap">
      {queries.map((q, qi) => (
        <div key={qi} className="sql-query-block">
          {/* Show SQL on expand */}
          {q.sql && (
            <details className="sql-details">
              <summary className="sql-summary">
                {q.purpose ? <span className="sql-purpose">{q.purpose}</span> : <span className="sql-purpose">query {qi+1}</span>}
                <span className="sql-row-count">{(q.row_count ?? q.rows?.length ?? 0)} rows</span>
              </summary>
              <pre className="sql-code">{q.sql}</pre>
            </details>
          )}
          {q.error && <div className="sql-error">Error: {q.error}</div>}
          {q.rows && q.rows.length > 0 && (
            <div className="result-table-wrap">
              <table className="result-table">
                <thead>
                  <tr>{Object.keys(q.rows[0]).map(k => <th key={k}>{k.replace(/([A-Z])/g, ' $1').trim()}</th>)}</tr>
                </thead>
                <tbody>
                  {q.rows.slice(0, 20).map((row, i) => (
                    <tr key={i}>
                      {Object.keys(q.rows[0]).map(k => <td key={k}>{row[k] != null ? String(row[k]) : '—'}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
              {q.rows.length > 20 && <p className="result-more">+{q.rows.length - 20} more rows</p>}
            </div>
          )}
          {q.rows && q.rows.length === 0 && !q.error && (
            <div className="sql-empty">No records found for this query.</div>
          )}
        </div>
      ))}
    </div>
  )
}


export default function ChatPanel({ onResult }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)
  // Conversation history — last 6 turns sent with every request for context
  const historyRef = useRef([])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const submit = useCallback(async (query) => {
    const text = (query ?? input).trim()
    if (!text || loading) return
    setInput('')
    setMessages(prev => [...prev, { id: Date.now(), role: 'user', text }])
    setLoading(true)
    const assistantId = Date.now() + 1
    setMessages(prev => [...prev, { id: assistantId, role: 'assistant', plan: null, result: null, nlAnswer: '', streaming: true }])

    // Snapshot history before this turn (last 6 entries = 3 exchanges)
    const historySnapshot = historyRef.current.slice(-6)

    try {
      const res = await fetch(API_STREAM, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: text, history: historySnapshot }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n'); buf = lines.pop()
        for (const line of lines) {
          if (!line.startsWith('data:')) continue
          try {
            const ev = JSON.parse(line.slice(5).trim())
            if (ev.type === 'plan') setMessages(p => p.map(m => m.id === assistantId ? { ...m, plan: ev.payload } : m))
            if (ev.type === 'result') { onResult?.(ev.payload); setMessages(p => p.map(m => m.id === assistantId ? { ...m, result: ev.payload } : m)) }
            if (ev.type === 'token') setMessages(p => p.map(m => m.id === assistantId ? { ...m, nlAnswer: (m.nlAnswer || '') + ev.payload } : m))
            if (ev.type === 'done') {
            setMessages(p => p.map(m => m.id === assistantId ? { ...m, streaming: false } : m))
          }
          } catch { /* skip */ }
        }
      }

      // Append this exchange to history for next query's context
      // Get the final nlAnswer from the current assistant message
      setMessages(current => {
        const assistantMsg = current.find(m => m.id === assistantId)
        const nlText = assistantMsg?.nlAnswer || ''
        const planIntent = assistantMsg?.plan?.intent || ''
        const resultSummary = assistantMsg?.result
          ? `[${planIntent} result: ${JSON.stringify(assistantMsg.result).slice(0, 200)}]`
          : ''
        const assistantSummary = nlText
          ? nlText.slice(0, 300)
          : resultSummary

        historyRef.current = [
          ...historyRef.current,
          { role: 'user', content: text },
          { role: 'assistant', content: assistantSummary },
        ].slice(-12) // keep last 6 exchanges = 12 turns

        return current
      })
    } catch (err) {
      setMessages(prev => prev.filter(m => m.id !== assistantId).concat([{ id: assistantId, role: 'error', text: err.message === 'Failed to fetch' ? 'Cannot reach backend. Make sure FastAPI is running on port 8000.' : `Error: ${err.message}` }]))
    } finally { setLoading(false); inputRef.current?.focus() }
  }, [input, loading, onResult])

  return (
    <div className="chat-panel">
      {/* Header */}
      <div className="chat-header">
        <div className="chat-header-avatar">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="10" fill="#1e293b"/>
            <path d="M8 12h8M12 8v8" stroke="white" strokeWidth="2" strokeLinecap="round"/>
          </svg>
        </div>
        <div>
          <div className="chat-header-name">Graph Agent</div>
          <div className="chat-header-sub">Order to Cash</div>
        </div>
        <span className="chat-header-status">
          <span className="status-dot-green" />
          awaiting instructions
        </span>
      </div>

      {/* Messages */}
      <div className="chat-messages">
        {/* Welcome */}
        {messages.length === 0 && (
          <div className="msg msg-assistant">
            <div className="msg-avatar">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="10" fill="#1e293b"/>
                <path d="M8 12h8M12 8v8" stroke="white" strokeWidth="2" strokeLinecap="round"/>
              </svg>
            </div>
            <div className="msg-content">
              <p className="msg-answer">Hi! I can help you analyze the <strong>Order to Cash</strong> process. Ask me about sales orders, deliveries, billing documents, payments, or data quality issues.</p>
              <div className="suggestions">
                {SUGGESTIONS.map(s => (
                  <button key={s} className="suggestion-btn" onClick={() => submit(s)}>{s}</button>
                ))}
              </div>
            </div>
          </div>
        )}

        {messages.map((msg, i) => <Message key={msg.id || i} msg={msg} />)}

        {loading && messages[messages.length - 1]?.streaming === true ? null : loading && (
          <div className="msg msg-assistant">
            <div className="msg-avatar">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="10" fill="#1e293b"/>
                <path d="M8 12h8M12 8v8" stroke="white" strokeWidth="2" strokeLinecap="round"/>
              </svg>
            </div>
            <div className="loading-dots"><span /><span /><span /></div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="chat-input-wrap">
        <textarea
          ref={inputRef}
          className="chat-input"
          rows={1}
          placeholder="Analyze anything"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() } }}
          disabled={loading}
        />
        <button
          className="send-btn"
          onClick={() => submit()}
          disabled={!input.trim() || loading}
        >
          Send
        </button>
      </div>
    </div>
  )
}
