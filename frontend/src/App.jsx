import { useEffect, useState, useCallback } from 'react'
import GraphView from './components/GraphView'
import ChatPanel from './components/ChatPanel'
import './App.css'

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

function buildGraphFromOverview(data) {
  const { nodes = [], edges = [] } = data
  const graphNodes = nodes.map(n => ({
    id: `${n.type}_${n.id}`,
    label: `${n.type.replace(/_/g, ' ')}\n${n.id}`,
    type: n.type,
    rawId: n.id,
    metadata: n.metadata || {},
  }))
  const graphEdges = edges.map((e, i) => ({
    id: `edge_${i}`,
    source: `${e.source.type}_${e.source.id}`,
    target: `${e.target.type}_${e.target.id}`,
    label: e.edge_type,
  }))
  return { nodes: graphNodes, edges: graphEdges }
}

function buildGraphFromResult(result) {
  if (!result) return null

  // trace_flow: has path.nodes + path.edges
  if (result.intent === 'trace_flow' && result.path) {
    const { nodes = [], edges = [] } = result.path
    const graphNodes = nodes.map(n => ({
      id: `${n.type}_${n.id}`,
      label: `${n.type.replace(/_/g, ' ')}\n${n.id}`,
      type: n.type,
      rawId: n.id,
      metadata: n.metadata || {},
    }))
    const graphEdges = edges.map((e, i) => ({
      id: `edge_${i}`,
      source: `${e.source.type}_${e.source.id}`,
      target: `${e.target.type}_${e.target.id}`,
      label: e.edge_type,
    }))
    return { nodes: graphNodes, edges: graphEdges, highlightedIds: graphNodes.map(n => n.id) }
  }

  // lookup_entity: show single entity node
  if (result.intent === 'lookup_entity' && result.entity && result.entity_type && result.entity_id) {
    const nodeId = `${result.entity_type}_${result.entity_id}`
    const nodes = [{
      id: nodeId,
      label: `${result.entity_type.replace(/_/g, ' ')}\n${result.entity_id}`,
      type: result.entity_type,
      rawId: result.entity_id,
      metadata: result.entity || {},
    }]
    // Add related billing docs as extra nodes if present
    const edges = []
    if (result.related?.billing_documents) {
      result.related.billing_documents.forEach((bd, i) => {
        const bdId = `billing_document_${bd.billingDocument}`
        nodes.push({
          id: bdId,
          label: `billing document\n${bd.billingDocument}`,
          type: 'billing_document',
          rawId: bd.billingDocument,
          metadata: bd,
        })
        edges.push({
          id: `rel_edge_${i}`,
          source: nodeId,
          target: bdId,
          label: 'BILLED_AS',
        })
      })
    }
    return { nodes, edges, highlightedIds: [nodeId] }
  }

  // top_products: show product nodes
  if (result.intent === 'top_products_by_billing' && result.results) {
    const nodes = result.results.slice(0, 20).map(r => ({
      id: `product_${r.product_id}`,
      label: `product\n${r.product_id}`,
      type: 'product',
      rawId: r.product_id,
      metadata: {
        total_net_amount: r.total_net_amount,
        invoice_count: r.invoice_count,
        quantity: r.quantity,
      },
    }))
    return { nodes, edges: [], highlightedIds: [] }
  }

  // find_broken_flows: show affected nodes
  if (result.intent === 'find_broken_flows' && result.issues) {
    const nodes = []
    const seen = new Set()
    result.issues.slice(0, 50).forEach((issue, i) => {
      const addNode = (type, id) => {
        const nodeId = `${type}_${id}`
        if (!seen.has(nodeId)) {
          seen.add(nodeId)
          nodes.push({
            id: nodeId,
            label: `${type.replace(/_/g, ' ')}\n${id}`,
            type,
            rawId: id,
            metadata: { break_type: issue.break_type },
          })
        }
      }
      if (issue.billing_document) addNode('billing_document', issue.billing_document)
      if (issue.delivery) addNode('delivery', issue.delivery)
      if (issue.accounting_document) addNode('accounting_document', issue.accounting_document)
    })
    return { nodes, edges: [], highlightedIds: nodes.map(n => n.id) }
  }

  return null
}

export default function App() {
  const [graphData, setGraphData] = useState({ nodes: [], edges: [] })
  const [highlightedIds, setHighlightedIds] = useState([])
  const [graphStatus, setGraphStatus] = useState('loading') // 'loading' | 'ok' | 'error'
  const [overviewData, setOverviewData] = useState(null)
  const [viewMode, setViewMode] = useState('overview') // 'overview' | 'query'

  // Load graph overview on mount
  useEffect(() => {
    setGraphStatus('loading')
    fetch(`${API_BASE}/graph/overview?max_edges=800`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(data => {
        const built = buildGraphFromOverview(data)
        setOverviewData(built)
        setGraphData(built)
        setGraphStatus('ok')
      })
      .catch(err => {
        console.error('Graph overview failed:', err)
        setGraphStatus('error')
      })
  }, [])

  const handleQueryResult = useCallback((result) => {
    if (!result) return
    if (result.intent === 'reject') return

    const built = buildGraphFromResult(result)
    if (!built) return

    setGraphData({ nodes: built.nodes, edges: built.edges })
    setHighlightedIds(built.highlightedIds || [])
    setViewMode('query')
  }, [])

  const handleResetGraph = useCallback(() => {
    if (overviewData) {
      setGraphData(overviewData)
      setHighlightedIds([])
      setViewMode('overview')
    }
  }, [overviewData])

  const nodeCount = graphData.nodes.length
  const edgeCount = graphData.edges.length

  return (
    <div className="app">
      <header className="app-header">
        <span className="app-logo">O2C</span>
        <span className="app-title">Order-to-Cash Graph Explorer</span>
        <div className="app-header-right">
          {viewMode === 'query' && (
            <button className="reset-btn" onClick={handleResetGraph}>
              ← Back to overview
            </button>
          )}
          <span className="app-stats">
            {nodeCount} nodes · {edgeCount} edges
          </span>
          <span className="app-status">
            <span className={`status-dot ${graphStatus === 'ok' ? 'status-ok' : graphStatus === 'error' ? 'status-error' : 'status-loading'}`} />
            {graphStatus === 'loading' ? 'loading…' : graphStatus === 'error' ? 'backend error' : 'connected'}
          </span>
        </div>
      </header>
      <main className="app-body">
        <section className="pane pane-graph">
          <GraphView
            nodes={graphData.nodes}
            edges={graphData.edges}
            highlightedIds={highlightedIds}
          />
        </section>
        <section className="pane pane-chat">
          <ChatPanel onResult={handleQueryResult} />
        </section>
      </main>
    </div>
  )
}
