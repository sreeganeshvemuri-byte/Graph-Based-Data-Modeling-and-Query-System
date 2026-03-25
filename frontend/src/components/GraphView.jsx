import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import cytoscape from 'cytoscape'
import './GraphView.css'

export const NODE_COLORS = {
  sales_order: '#7c3aed',
  delivery: '#0d9488',
  billing_document: '#ea580c',
  accounting_document: '#ca8a04',
  customer: '#2563eb',
  payment: '#16a34a',
  schedule_line: '#db2777',
  product: '#6366f1',
}

function pretty(text) {
  return String(text).replace(/_/g, ' ')
}

export default function GraphView({ nodes, edges, highlightedIds = [] }) {
  const cyRef = useRef(null)
  const containerRef = useRef(null)
  const [selectedNode, setSelectedNode] = useState(null)

  // Build cytoscape elements — MUST wrap in data: {}
  const elements = useMemo(() => {
    const nodeEls = nodes.map(n => ({
      group: 'nodes',
      data: {
        id: n.id,
        label: n.label || `${pretty(n.type)}\n${n.rawId}`,
        type: n.type,
        rawId: n.rawId,
        metadata: n.metadata || {},
      },
    }))

    const edgeEls = edges
      .filter(e => e.source && e.target)
      .map(e => ({
        group: 'edges',
        data: {
          id: e.id,
          source: e.source,
          target: e.target,
          label: pretty(e.label || e.edge_type || ''),
        },
      }))

    return [...nodeEls, ...edgeEls]
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
            'font-size': 10,
            'color': '#e2e8f0',
            'background-color': '#475569',
            'border-width': 2,
            'border-color': '#cbd5e1',
            'width': 140,
            'height': 56,
            'shape': 'round-rectangle',
          },
        },
        // Color per node type
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
        {
          selector: 'node.highlighted',
          style: {
            'border-color': '#fbbf24',
            'border-width': 3,
            'background-opacity': 1,
            'shadow-blur': 18,
            'shadow-color': '#fbbf24',
            'shadow-opacity': 0.8,
            'shadow-offset-x': 0,
            'shadow-offset-y': 0,
          },
        },
        {
          selector: 'node.dimmed',
          style: {
            'opacity': 0.25,
          },
        },
      ],
      layout: { name: 'breadthfirst', directed: true, padding: 40 },
      wheelSensitivity: 0.2,
    })

    cy.on('select', 'node', evt => {
      setSelectedNode(evt.target.data())
    })
    cy.on('unselect', 'node', () => {
      setSelectedNode(null)
    })

    cyRef.current = cy

    return () => {
      cy.destroy()
      cyRef.current = null
    }
  }, [])

  // Update graph elements when data changes
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return

    cy.elements().remove()
    setSelectedNode(null)

    if (!elements.length) return

    cy.add(elements)

    const layoutName = nodes.length > 50 ? 'cose' : 'breadthfirst'
    cy.layout({
      name: layoutName,
      directed: true,
      padding: 40,
      spacingFactor: 1.4,
      animate: false,
    }).run()
    cy.fit(undefined, 40)
  }, [elements])

  // Highlight specific nodes + dim others
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    cy.nodes().removeClass('highlighted').removeClass('dimmed')
    if (highlightedIds.length) {
      const idSet = new Set(highlightedIds)
      cy.nodes().forEach(node => {
        if (idSet.has(node.id())) {
          node.addClass('highlighted')
        } else {
          node.addClass('dimmed')
        }
      })
      // Fit to highlighted nodes
      const highlighted = cy.nodes('.highlighted')
      if (highlighted.length > 0) {
        cy.animate({ fit: { eles: highlighted, padding: 60 } }, { duration: 400 })
      }
    }
  }, [highlightedIds])

  const handleFit = useCallback(() => cyRef.current?.fit(undefined, 40), [])
  const handleZoomIn = useCallback(() => {
    const cy = cyRef.current
    if (cy) cy.zoom(cy.zoom() * 1.2)
  }, [])
  const handleZoomOut = useCallback(() => {
    const cy = cyRef.current
    if (cy) cy.zoom(cy.zoom() * 0.8)
  }, [])

  const isEmpty = nodes.length === 0

  return (
    <div className="graph-view">
      <div className="graph-toolbar">
        <span className="graph-label">Graph Explorer</span>
        <div className="graph-legend">
          {Object.entries(NODE_COLORS).map(([type, color]) => (
            <span key={type} className="legend-item">
              <span className="legend-dot" style={{ background: color }} />
              {pretty(type)}
            </span>
          ))}
        </div>
        <div className="graph-controls">
          <button onClick={handleZoomIn} title="Zoom In">+</button>
          <button onClick={handleZoomOut} title="Zoom Out">−</button>
          <button onClick={handleFit} title="Fit to screen">⊡</button>
        </div>
      </div>

      <div className="graph-canvas" ref={containerRef} />

      <div className="meta-panel">
        {!selectedNode ? (
          <p className="meta-empty">Click a node to inspect its metadata.</p>
        ) : (
          <>
            <h4 className="meta-title">
              <span className="meta-badge" style={{ background: NODE_COLORS[selectedNode.type] || '#475569' }}>
                {pretty(selectedNode.type)}
              </span>
              <span className="meta-id">{selectedNode.rawId}</span>
            </h4>
            <pre className="meta-pre">{JSON.stringify(selectedNode.metadata || {}, null, 2)}</pre>
          </>
        )}
      </div>

      {isEmpty && (
        <div className="graph-empty">
          <div className="graph-empty-icon">◈</div>
          <p>Loading the O2C graph…</p>
          <p className="graph-empty-hint">Or run a query to trace a specific flow</p>
        </div>
      )}
    </div>
  )
}
