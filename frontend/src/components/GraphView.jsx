import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import cytoscape from 'cytoscape'
import './GraphView.css'

const NODE_COLORS = {
  sales_order:        '#6366f1',
  delivery:           '#0891b2',
  billing_document:   '#dc2626',
  accounting_document:'#d97706',
  customer:           '#2563eb',
  payment:            '#16a34a',
  schedule_line:      '#9333ea',
  product:            '#0d9488',
}

function pretty(text) {
  return String(text).replace(/_/g, ' ')
}

function NodeTooltip({ node, onClose }) {
  if (!node) return null
  const meta = node.metadata || {}
  const entries = Object.entries(meta).filter(([, v]) => v !== null && v !== undefined && v !== '')

  return (
    <div className="node-tooltip">
      <div className="node-tooltip-header">
        <span
          className="node-tooltip-type"
          style={{ background: NODE_COLORS[node.type] || '#64748b' }}
        >
          {pretty(node.type)}
        </span>
        <span className="node-tooltip-id">{node.rawId}</span>
        <button className="node-tooltip-close" onClick={onClose}>✕</button>
      </div>
      {entries.length > 0 ? (
        <div className="node-tooltip-body">
          {entries.map(([k, v]) => (
            <div key={k} className="node-tooltip-row">
              <span className="node-tooltip-key">{pretty(k)}</span>
              <span className="node-tooltip-val">{String(v)}</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="node-tooltip-empty">No metadata available</div>
      )}
    </div>
  )
}

export default function GraphView({ nodes, edges, highlightedIds = [], onResetView }) {
  const cyRef = useRef(null)
  const containerRef = useRef(null)
  const [selectedNode, setSelectedNode] = useState(null)
  const [edgesVisible, setEdgesVisible] = useState(true)

  const elements = useMemo(() => {
    const nodeEls = nodes.map(n => ({
      group: 'nodes',
      data: { id: n.id, label: n.label, type: n.type, rawId: n.rawId, metadata: n.metadata || {} },
    }))
    const edgeEls = edges
      .filter(e => e.source && e.target)
      .map(e => ({
        group: 'edges',
        data: { id: e.id, source: e.source, target: e.target, label: e.label || '' },
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
            'width': 12,
            'height': 12,
            'shape': 'ellipse',
            'background-color': '#94a3b8',
            'border-width': 0,
            'label': '',  // NO labels shown by default
          },
        },
        // Per-type colors
        ...Object.entries(NODE_COLORS).map(([type, color]) => ({
          selector: `node[type = "${type}"]`,
          style: { 'background-color': color },
        })),
        {
          selector: 'edge',
          style: {
            'curve-style': 'bezier',
            'width': 1.5,
            'line-color': '#93c5fd',
            'target-arrow-color': '#93c5fd',
            'target-arrow-shape': 'vee',
            'arrow-scale': 0.8,
            'opacity': 0.85,
          },
        },
        {
          selector: 'node:selected',
          style: {
            'border-width': 3,
            'border-color': '#1e293b',
            'width': 16,
            'height': 16,
          },
        },
        // Highlighted nodes (from query results)
        {
          selector: 'node.highlighted',
          style: {
            'width': 18,
            'height': 18,
            'border-width': 3,
            'border-color': '#ffffff',
            'shadow-blur': 20,
            'shadow-color': 'data(color)',
            'shadow-opacity': 0.9,
            'shadow-offset-x': 0,
            'shadow-offset-y': 0,
            'background-opacity': 1,
          },
        },
        {
          selector: 'node.dimmed',
          style: { 'opacity': 0.1 },
        },
        {
          selector: 'edge.dimmed',
          style: { 'opacity': 0.1 },
        },
        {
          selector: 'edge.highlighted-edge',
          style: {
            'line-color': '#6366f1',
            'target-arrow-color': '#6366f1',
            'width': 2,
            'opacity': 1,
          },
        },
      ],
      layout: { name: 'preset' },
      wheelSensitivity: 0.3,
      minZoom: 0.1,
      maxZoom: 8,
    })

    cy.on('tap', 'node', evt => {
      const d = evt.target.data()
      setSelectedNode(d)
    })
    cy.on('tap', evt => {
      if (evt.target === cy) setSelectedNode(null)
    })

    cyRef.current = cy
    return () => { cy.destroy(); cyRef.current = null }
  }, [])

  // Update elements
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    cy.elements().remove()
    setSelectedNode(null)
    if (!elements.length) return

    cy.add(elements)

    const layoutName = nodes.length > 80 ? 'cose' : 'breadthfirst'
    cy.layout({
      name: layoutName,
      directed: true,
      padding: 60,
      spacingFactor: nodes.length > 200 ? 1.0 : 1.6,
      animate: false,
      nodeRepulsion: () => 4000,
      idealEdgeLength: () => 80,
      edgeElasticity: () => 100,
    }).run()
    cy.fit(undefined, 60)
  }, [elements])

  // Highlighting
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    cy.elements().removeClass('highlighted').removeClass('dimmed').removeClass('highlighted-edge')

    if (highlightedIds.length) {
      const idSet = new Set(highlightedIds)
      cy.nodes().forEach(n => {
        if (idSet.has(n.id())) n.addClass('highlighted')
        else n.addClass('dimmed')
      })
      cy.edges().forEach(e => {
        const srcHl = idSet.has(e.source().id())
        const tgtHl = idSet.has(e.target().id())
        if (srcHl && tgtHl) e.addClass('highlighted-edge')
        else e.addClass('dimmed')
      })
      const hl = cy.nodes('.highlighted')
      if (hl.length) cy.animate({ fit: { eles: hl, padding: 80 } }, { duration: 500 })
    }
  }, [highlightedIds])

  const handleFit = useCallback(() => cyRef.current?.fit(undefined, 60), [])

  // Toggle edge visibility
  const handleEdgeToggle = useCallback(() => {
    const cy = cyRef.current
    if (!cy) return
    const next = !edgesVisible
    setEdgesVisible(next)
    cy.edges().style({ opacity: next ? 0.85 : 0 })
  }, [edgesVisible])

  const isEmpty = nodes.length === 0

  return (
    <div className="graph-view">
      {/* Minimal toolbar */}
      <div className="graph-toolbar">
        <div className="graph-legend">
          {Object.entries(NODE_COLORS).map(([type, color]) => (
            <span key={type} className="legend-item">
              <span className="legend-dot" style={{ background: color }} />
              {pretty(type)}
            </span>
          ))}
        </div>
        <div className="graph-controls">
          {/* Revert to full graph — only shown when query is active */}
          {onResetView && (
            <button onClick={onResetView} title="Back to full graph" className="btn-reset-view">
              ↩ Overview
            </button>
          )}
          {/* Edge dimming toggle */}
          <button
            onClick={handleEdgeToggle}
            title={edgesVisible ? 'Hide edges' : 'Show edges'}
            className={`btn-edge-toggle ${edgesVisible ? 'active' : ''}`}
          >
            {edgesVisible ? '⌇ Edges' : '⌇ Edges'}
          </button>
          <button onClick={() => cyRef.current?.zoom(cyRef.current.zoom() * 1.25)} title="Zoom in">+</button>
          <button onClick={() => cyRef.current?.zoom(cyRef.current.zoom() * 0.8)} title="Zoom out">−</button>
          <button onClick={handleFit} title="Fit to screen">⊡</button>
        </div>
      </div>

      {/* Canvas */}
      <div className="graph-canvas" ref={containerRef} />

      {/* Floating node tooltip — only shown on click */}
      {selectedNode && (
        <NodeTooltip node={selectedNode} onClose={() => setSelectedNode(null)} />
      )}

      {isEmpty && (
        <div className="graph-empty">
          <div className="graph-empty-icon">◎</div>
          <p>Loading graph…</p>
        </div>
      )}
    </div>
  )
}
