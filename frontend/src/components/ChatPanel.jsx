import { useState, useRef, useEffect, useCallback } from 'react'
import './ChatPanel.css'

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
const API_STREAM = `${API_BASE}/query/stream`

const SUGGESTIONS = [
  'Show me the full journey for sales order 740509',
  'Trace the full flow of billing document 90504274',
  'Which products are associated with the highest number of billing documents?',
  'Find all deliveries with no sales order',
  'Show data quality issues in the dataset',
  'Look up customer 310000108',
  'Identify sales orders with broken or incomplete flows',
]

function PlanBlock({ plan }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="plan-block">
      <button className="plan-toggle" onClick={() => setOpen(o => !o)}>
        <span className={`plan-arrow ${open ? 'open' : ''}`}>▶</span>
        <span className="plan-badge">{plan.intent}</span>
        <span className="plan-toggle-label">query plan</span>
      </button>
      {open && <pre className="plan-json">{JSON.stringify(plan, null, 2)}</pre>}
    </div>
  )
}

function ResultTable({ rows }) {
  if (!rows || rows.length === 0) return null
  const keys = Object.keys(rows[0])
  return (
    <div className="result-table-wrap">
      <table className="result-table">
        <thead>
          <tr>{keys.map(k => <th key={k}>{k.replace(/_/g, ' ')}</th>)}</tr>
        </thead>
        <tbody>
          {rows.slice(0, 20).map((row, i) => (
            <tr key={i}>
              {keys.map(k => <td key={k}>{row[k] != null ? String(row[k]) : '—'}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > 20 && <p className="result-more">…and {rows.length - 20} more</p>}
    </div>
  )
}

function IssuesList({ issues }) {
  if (!issues || issues.length === 0) return <p className="no-issues">✓ No issues found</p>
  return (
    <div className="issues-list">
      {issues.slice(0, 15).map((issue, i) => (
        <div key={i} className="issue-item">
          <span className="issue-type">{issue.break_type?.replace(/_/g, ' ')}</span>
          <span className="issue-detail">
            {issue.billing_document && `Billing: ${issue.billing_document}`}
            {issue.delivery && `Delivery: ${issue.delivery}`}
            {issue.accounting_document && `Acct: ${issue.accounting_document}`}
            {issue.diff !== undefined && ` (diff: ${issue.diff?.toFixed(2)})`}
          </span>
        </div>
      ))}
      {issues.length > 15 && <p className="result-more">…and {issues.length - 15} more issues</p>}
    </div>
  )
}

function StreamingText({ text, streaming }) {
  return (
    <p className="msg-summary">
      {text}
      {streaming && <span className="stream-cursor">▋</span>}
    </p>
  )
}

function Message({ msg }) {
  if (msg.role === 'user') {
    return (
      <div className="msg msg-user">
        <span className="msg-bubble">{msg.text}</span>
      </div>
    )
  }
  if (msg.role === 'error') {
    return (
      <div className="msg msg-error">
        <span className="msg-icon">⚠</span>
        <span className="msg-bubble">{msg.text}</span>
      </div>
    )
  }

  const { plan, result, nlAnswer, streaming } = msg

  return (
    <div className="msg msg-assistant">
      <div className="msg-content">
        {plan && <PlanBlock plan={plan} />}

        {/* Stats pills */}
        {result && plan?.intent !== 'reject' && (
          <div className="msg-stats">
            {result.path?.nodes?.length > 0 && (
              <span className="stat-pill">📊 {result.path.nodes.length} nodes</span>
            )}
            {result.path?.edges?.length > 0 && (
              <span className="stat-pill">🔗 {result.path.edges.length} edges</span>
            )}
            {result.results?.length > 0 && (
              <span className="stat-pill">📋 {result.results.length} products</span>
            )}
            {result.intent === 'find_broken_flows' && (
              <span className={`stat-pill ${result.issues?.length > 0 ? 'stat-pill-warn' : 'stat-pill-ok'}`}>
                {result.issues?.length > 0 ? `⚠ ${result.issues.length} issues` : '✓ No issues'}
              </span>
            )}
          </div>
        )}

        {/* Streaming NL answer */}
        {(nlAnswer !== undefined) && (
          <StreamingText text={nlAnswer} streaming={streaming} />
        )}

        {/* Inline data tables */}
        {result?.intent === 'top_products_by_billing' && <ResultTable rows={result.results} />}
        {result?.intent === 'find_broken_flows' && <IssuesList issues={result.issues} />}

        {result?.intent === 'lookup_entity' && result.entity && (
          <div className="entity-card">
            <div className="entity-card-header">
              {result.entity_type?.replace(/_/g, ' ')} · {result.entity_id}
            </div>
            <pre className="entity-pre">{JSON.stringify(result.entity, null, 2)}</pre>
            {result.related && Object.keys(result.related).length > 0 && (
              <details className="related-details">
                <summary>Related: {Object.keys(result.related).join(', ')}</summary>
                <pre className="entity-pre">{JSON.stringify(result.related, null, 2)}</pre>
              </details>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default function ChatPanel({ onResult }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)
  const abortRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const submit = useCallback(async (query) => {
    const text = (query ?? input).trim()
    if (!text || loading) return

    setInput('')
    setMessages(prev => [...prev, { role: 'user', text }])
    setLoading(true)

    // Add placeholder assistant message
    const assistantIdx = Date.now()
    setMessages(prev => [...prev, {
      role: 'assistant',
      id: assistantIdx,
      plan: null,
      result: null,
      nlAnswer: '',
      streaming: true,
    }])

    try {
      const res = await fetch(API_STREAM, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: text }),
        signal: abortRef.current?.signal,
      })

      if (!res.ok) throw new Error(`HTTP ${res.status}`)

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let planData = null
      let resultData = null

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() // keep incomplete line

        for (const line of lines) {
          if (!line.startsWith('data:')) continue
          const raw = line.slice(5).trim()
          if (!raw) continue

          let event
          try { event = JSON.parse(raw) } catch { continue }

          if (event.type === 'plan') {
            planData = event.payload
            setMessages(prev => prev.map(m =>
              m.id === assistantIdx ? { ...m, plan: planData } : m
            ))
          }

          if (event.type === 'result') {
            resultData = event.payload
            onResult?.(resultData)
            setMessages(prev => prev.map(m =>
              m.id === assistantIdx ? { ...m, result: resultData } : m
            ))
          }

          if (event.type === 'token') {
            const token = event.payload
            setMessages(prev => prev.map(m =>
              m.id === assistantIdx
                ? { ...m, nlAnswer: (m.nlAnswer || '') + token }
                : m
            ))
          }

          if (event.type === 'done') {
            setMessages(prev => prev.map(m =>
              m.id === assistantIdx ? { ...m, streaming: false } : m
            ))
          }
        }
      }
    } catch (err) {
      if (err.name === 'AbortError') return
      setMessages(prev => {
        // Replace placeholder with error
        const filtered = prev.filter(m => m.id !== assistantIdx)
        return [...filtered, {
          role: 'error',
          text: err.message === 'Failed to fetch'
            ? `Cannot reach backend at ${API_STREAM}.`
            : `Error: ${err.message}`,
        }]
      })
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }, [input, loading, onResult])

  function onKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  const showSuggestions = messages.length === 0

  return (
    <div className="chat-panel">
      <div className="chat-header">
        <span className="chat-label">Natural Language Query</span>
        <span className="chat-hint">O2C dataset only</span>
      </div>

      <div className="chat-messages">
        {showSuggestions && (
          <div className="suggestions">
            <p className="suggestions-label">Try a query</p>
            {SUGGESTIONS.map(s => (
              <button key={s} className="suggestion-btn" onClick={() => submit(s)}>
                {s}
              </button>
            ))}
          </div>
        )}

        {messages.map((msg, i) => <Message key={msg.id || i} msg={msg} />)}

        {loading && messages[messages.length - 1]?.role !== 'assistant' && (
          <div className="msg msg-assistant">
            <div className="loading-dots"><span /><span /><span /></div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <div className="chat-input-row">
        <textarea
          ref={inputRef}
          className="chat-input"
          rows={1}
          placeholder="Ask about orders, deliveries, billing…"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={onKey}
          disabled={loading}
        />
        <button
          className="send-btn"
          onClick={() => submit()}
          disabled={!input.trim() || loading}
        >
          ↑
        </button>
      </div>
    </div>
  )
}
