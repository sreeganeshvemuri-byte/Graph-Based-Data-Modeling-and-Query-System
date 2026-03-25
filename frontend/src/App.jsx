import { useEffect, useState } from 'react'
import GraphView from './components/GraphView'
import ChatPanel from './components/ChatPanel'
import './App.css'

export default function App() {
  const [graphData, setGraphData] = useState({ nodes: [], edges: [] })


  useEffect(() => {
    let cancelled = false

    async function loadOverview() {
      try {
        const res = await fetch('/api/graph/overview?max_edges=1200')
        if (!res.ok) return
        const data = await res.json()
        if (cancelled) return

        const graphNodes = (data.nodes || []).map(n => ({
          id: `${n.type}_${n.id}`,
          label: `${n.type.replace(/_/g, ' ')}\n${n.id}`,
          type: n.type,
          rawId: n.id,
          metadata: n.metadata || {},
        }))

        const graphEdges = (data.edges || []).map((e, i) => ({
          id: `edge_boot_${i}`,
          source: `${e.source.type}_${e.source.id}`,
          target: `${e.target.type}_${e.target.id}`,
          label: e.edge_type,
        }))

        setGraphData({ nodes: graphNodes, edges: graphEdges })
      } catch {
        // keep empty graph if backend is unavailable
      }
    }

    loadOverview()
    return () => {
      cancelled = true
    }
  }, [])

  function handleQueryResult(result) {
    if (!result?.path) return

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

    setGraphData({ nodes: graphNodes, edges: graphEdges })
  }

  return (
    <div className="app">
      <header className="app-header">
        <span className="app-logo">O2C</span>
        <span className="app-title">Order-to-Cash Explorer</span>
        <span className="app-status">
          <span className="status-dot" />
          connected
        </span>
      </header>
      <main className="app-body">
        <section className="pane pane-graph">
          <GraphView nodes={graphData.nodes} edges={graphData.edges} />
        </section>
        <section className="pane pane-chat">
          <ChatPanel onResult={handleQueryResult} />
        </section>
      </main>
    </div>
  )
}
