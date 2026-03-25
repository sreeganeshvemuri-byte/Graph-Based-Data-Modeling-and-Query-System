import { useEffect, useRef } from 'react'
import cytoscape from 'cytoscape'
import './GraphView.css'

const NODE_COLORS = {
  sales_order:          { bg: '#7c3aed', border: '#5b21b6', text: '#ede9fe' },
  delivery:             { bg: '#0d9488', border: '#0f766e', text: '#ccfbf1' },
  billing_document:     { bg: '#ea580c', border: '#c2410c', text: '#ffedd5' },
  accounting_document:  { bg: '#ca8a04', border: '#a16207', text: '#fef9c3' },
}
const DEFAULT_COLOR = { bg: '#475569', border: '#334155', text: '#f1f5f9' }

function buildStylesheet() {
  const nodeStyles = Object.entries(NODE_COLORS).map(([type, c]) => ({
    selector: `node[type="${type}"]`,
    style: {
      'background-color': c.bg,
      'border-color': c.border,
      'color': c.text,
    }
  }))

  return [
    {
      selector: 'node',
      style: {
        'background-color': DEFAULT_COLOR.bg,
        'border-color': DEFAULT_COLOR.border,
        'border-width': 2,
        'color': DEFAULT_COLOR.text,
        'label': 'data(label)',
        'text-wrap': 'wrap',
        'text-max-width': 120,
        'text-valign': 'center',
        'text-halign': 'center',
        'font-size': 11,
        'font-family': '"JetBrains Mono", "Fira Code", monospace',
        'font-weight': 500,
        'width': 130,
        'height': 52,
        'shape': 'round-rectangle',
        'padding': 10,
        'transition-property': 'background-color, border-color, border-width, opacity',
        'transition-duration': '200ms',
      }
    },
    ...nodeStyles,
    {
      selector: 'node.dimmed',
      style: { 'opacity': 0.25 }
    },
    {
      selector: 'node.highlighted',
      style: {
        'border-width': 3,
        'border-color': '#f8fafc',
        'opacity': 1,
      }
    },
    {
      selector: 'edge',
      style: {
        'width': 1.5,
        'line-color': '#334155',
        'target-arrow-color': '#334155',
        'target-arrow-shape': 'triangle',
        'curve-style': 'bezier',
        'label': 'data(label)',
        'font-size': 9,
        'font-family': '"JetBrains Mono", "Fira Code", monospace',
        'color': '#94a3b8',
        'text-background-color': '#0f172a',
        'text-background-opacity': 1,
        'text-background-padding': 3,
        'text-rotation': 'autorotate',
        'transition-property': 'line-color, target-arrow-color, opacity, width',
        'transition-duration': '200ms',
      }
    },
    {
      selector: 'edge.dimmed',
      style: { 'opacity': 0.15 }
    },
    {
      selector: 'edge.highlighted',
      style: {
        'line-color': '#94a3b8',
        'target-arrow-color': '#94a3b8',
        'width': 2.5,
        'opacity': 1,
      }
    },
  ]
}

export default function GraphView({ nodes, edges, highlightedIds }) {
  const containerRef = useRef(null)
  const cyRef = useRef(null)

  useEffect(() => {
    if (!containerRef.current) return

    cyRef.current = cytoscape({
      container: containerRef.current,
      elements: [],
      style: buildStylesheet(),
      layout: { name: 'preset' },
      userZoomingEnabled: true,
      userPanningEnabled: true,
      boxSelectionEnabled: false,
      minZoom: 0.2,
      maxZoom: 3,
    })

    return () => {
      cyRef.current?.destroy()
      cyRef.current = null
    }
  }, [])

  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return

    cy.elements().remove()

    if (nodes.length === 0) return

    cy.add([...nodes, ...edges])

    cy.layout({
      name: 'breadthfirst',
      directed: true,
      padding: 40,
      spacingFactor: 1.4,
      animate: true,
      animationDuration: 500,
      fit: true,
    }).run()
  }, [nodes, edges])

  useEffect(() => {
    const cy = cyRef.current
    if (!cy || highlightedIds.size === 0) return

    cy.elements().addClass('dimmed').removeClass('highlighted')
    cy.elements().filter(el => highlightedIds.has(el.id()))
      .removeClass('dimmed').addClass('highlighted')
  }, [highlightedIds])

  const isEmpty = nodes.length === 0

  return (
    <div className="graph-view">
      <div className="graph-toolbar">
        <span className="graph-label">Graph</span>
        <div className="graph-legend">
          {Object.entries(NODE_COLORS).map(([type, c]) => (
            <span key={type} className="legend-item">
              <span className="legend-dot" style={{ background: c.bg }} />
              {type.replace(/_/g, ' ')}
            </span>
          ))}
        </div>
        <div className="graph-controls">
          <button onClick={() => cyRef.current?.fit(undefined, 40)} title="Fit to view">⊡</button>
          <button onClick={() => cyRef.current?.zoom(cyRef.current.zoom() * 1.2)} title="Zoom in">+</button>
          <button onClick={() => cyRef.current?.zoom(cyRef.current.zoom() / 1.2)} title="Zoom out">−</button>
        </div>
      </div>

      <div className="graph-canvas" ref={containerRef} />

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