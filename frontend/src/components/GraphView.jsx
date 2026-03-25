import { useEffect, useMemo, useRef, useState } from 'react'
import cytoscape from 'cytoscape'
import './GraphView.css'

const NODE_COLORS = {
  sales_order: '#7c3aed',
  delivery: '#0d9488',
  billing_document: '#ea580c',
  accounting_document: '#ca8a04',
  customer: '#2563eb',
  payment: '#16a34a',
}

function pretty(text) {
  return String(text).replace(/_/g, ' ')
}

export default function GraphView({ nodes, edges }) {
  const cyRef = useRef(null)
  const containerRef = useRef(null)
  const [selectedNode, setSelectedNode] = useState(null)

  const elements = useMemo(() => {
    return [
      ...nodes.map(n => ({ data: { ...n } })),
      ...edges.map(e => ({ data: { ...e } })),
    ]
  }, [nodes, edges])

  useEffect(() => {
    if (!containerRef.current) return

    const cy = cytoscape({
      container: containerRef.current,
      elements: [],
      style: [
        {
          selector: 'node',
          style: {
            'label': 'data(label)',
            'text-wrap': 'wrap',
            'text-max-width': 120,
            'text-valign': 'center',
            'text-halign': 'center',
            'font-size': 11,
            'color': '#e2e8f0',
            'background-color': '#475569',
            'border-width': 2,
            'border-color': '#cbd5e1',
            'width': 130,
            'height': 54,
            'shape': 'round-rectangle',
          },
        },
        ...Object.entries(NODE_COLORS).map(([type, color]) => ({
          selector: `node[type = "${type}"]`,
          style: { 'background-color': color },
        })),
        {
          selector: 'edge',
          style: {
            'curve-style': 'bezier',
            'width': 2,
            'line-color': '#64748b',
            'target-arrow-color': '#64748b',
            'target-arrow-shape': 'triangle',
            'label': 'data(label)',
            'font-size': 9,
            'color': '#94a3b8',
            'text-background-color': '#0f172a',
            'text-background-opacity': 1,
            'text-background-padding': 2,
          },
        },
        {
          selector: 'node:selected',
          style: {
            'border-color': '#f8fafc',
            'border-width': 4,
          },
        },
      ],
      layout: { name: 'breadthfirst', directed: true, padding: 40 },
      wheelSensitivity: 0.2,
    })

    cy.on('select', 'node', evt => {
      const d = evt.target.data()
      setSelectedNode(d)
    })

    cyRef.current = cy

    return () => {
      cy.destroy()
      cyRef.current = null
    }
  }, [])

  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return

    cy.elements().remove()
    if (!elements.length) {
      setSelectedNode(null)
      return
    }

    cy.add(elements)
    cy.layout({ name: 'breadthfirst', directed: true, padding: 40, spacingFactor: 1.3 }).run()
    cy.fit(undefined, 40)
  }, [elements])

  const isEmpty = nodes.length === 0

  return (
    <div className="graph-view">
      <div className="graph-toolbar">
        <span className="graph-label">3D-style Graph</span>
        <div className="graph-legend">
          {Object.entries(NODE_COLORS).map(([type, color]) => (
            <span key={type} className="legend-item">
              <span className="legend-dot" style={{ background: color }} />
              {pretty(type)}
            </span>
          ))}
        </div>
        <div className="graph-controls">
          <button onClick={() => cyRef.current?.fit(undefined, 40)} title="Fit">⊡</button>
        </div>
      </div>

      <div className="graph-canvas" ref={containerRef} />

      <div className="meta-panel">
        {!selectedNode ? (
          <p className="meta-empty">Select a node to inspect metadata.</p>
        ) : (
          <>
            <h4>{pretty(selectedNode.type)} · {selectedNode.rawId}</h4>
            <pre>{JSON.stringify(selectedNode.metadata || {}, null, 2)}</pre>
          </>
        )}
      </div>

      {isEmpty && (
        <div className="graph-empty">
          <div className="graph-empty-icon">◈</div>
          <p>Run a query to visualise the O2C flow</p>
          <p className="graph-empty-hint">Try: "Show me the full journey for sales order 740509"</p>
        </div>
      )}
    </div>
  )
}
