import { useState, useRef, useEffect } from 'react'
import './ChatPanel.css'

const API = 'http://localhost:8000/api/query'

const SUGGESTIONS = [
  'Show me the full journey for sales order 740509',
  'What happened to billing doc 90504274?',
  'Top 10 products by revenue this April',
  'Find all deliveries with no sales order',
  'Show data quality issues for fiscal year 2025',
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
      {open && (
        <pre className="plan-json">{JSON.stringify(plan, null, 2)}</pre>
      )}
    </div>
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

  return (
    <div className="msg msg-assistant">
      <div className="msg-content">
        {msg.plan && <PlanBlock plan={msg.plan} />}
        {msg.summary && <p className="msg-summary">{msg.summary}</p>}
        {msg.result && (
          <div className="msg-stats">
            {msg.result.path?.nodes?.length > 0 && (
              <span className="stat-pill">
                {msg.result.path.nodes.length} nodes
              </span>
            )}
            {msg.result.path?.edges?.length > 0 && (
              <span className="stat-pill">
                {msg.result.path.edges.length} edges
              </span>
            )}
            {msg.result.rows?.length > 0 && (
              <span className="stat-pill">
                {msg.result.rows.length} rows
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function buildSummary(plan, result) {
  if (!plan) return 'Query executed.'

  if (plan.intent === 'reject') {
    return plan.clarification_needed || 'Query rejected.'
  }
  if (plan.intent === 'trace_flow') {
    const n = result?.path?.nodes?.length ?? 0
    const e = result?.path?.edges?.length ?? 0
    return `Traced ${plan.entity_type} ${plan.entity_id} — found ${n} nodes across ${e} edges.`
  }
  if (plan.intent === 'lookup_entity') {
    return `Looking up ${plan.entity_type} ${plan.entity_id}.`
  }
  if (plan.intent === 'top_products_by_billing') {
    return `Top ${plan.limit} products by ${plan.sort_by.replace(/_/g, ' ')}.`
  }
  if (plan.intent === 'find_broken_flows') {
    return `Checking ${plan.break_types.length} break type(s).`
  }
  return 'Query executed.'
}

export default function ChatPanel({ onResult }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function submit(query) {
    const text = query ?? input.trim()
    if (!text || loading) return

    setInput('')
    setMessages(prev => [...prev, { role: 'user', text }])
    setLoading(true)

    try {
      const res = await fetch(API, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: text }),
      })

      if (!res.ok) throw new Error(`HTTP ${res.status}`)

      const data = await res.json()
      const { plan, result } = data

      onResult?.(result)

      setMessages(prev => [...prev, {
        role: 'assistant',
        plan,
        result,
        summary: buildSummary(plan, result),
      }])
    } catch (err) {
      setMessages(prev => [...prev, {
        role: 'error',
        text: err.message === 'Failed to fetch'
          ? 'Cannot reach backend at localhost:8000. Is FastAPI running?'
          : `Error: ${err.message}`,
      }])
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

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
        <span className="chat-label">Query</span>
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

        {messages.map((msg, i) => <Message key={i} msg={msg} />)}

        {loading && (
          <div className="msg msg-assistant">
            <div className="loading-dots">
              <span /><span /><span />
            </div>
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