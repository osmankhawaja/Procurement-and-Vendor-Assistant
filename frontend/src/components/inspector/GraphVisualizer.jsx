export default function GraphVisualizer({ definition = "" }) {
  const mermaidSource = typeof definition === "string" ? definition.trim() : "";

  return (
    <div className="graph-visualizer">
      <div
        className="graph-scroll"
        role="region"
        aria-label="Procurement workflow diagram"
        tabIndex={0}
      >
        <svg
          className="workflow-graph"
          viewBox="0 0 1000 350"
          role="img"
          aria-labelledby="workflow-graph-title workflow-graph-description"
        >
          <title id="workflow-graph-title">Procurement workflow</title>
          <desc id="workflow-graph-description">
            Requests pass through an input guardrail and procurement agent.
            Blocked requests end. Other requests route through manager approval
            when required, then pass an output guardrail before completion.
            Rejected requests return to the procurement agent.
          </desc>
          <defs>
            <marker
              id="workflow-arrow"
              markerWidth="8"
              markerHeight="8"
              refX="6"
              refY="3"
              orient="auto"
              markerUnits="strokeWidth"
              aria-hidden="true"
            >
              <path d="M0,0 L0,6 L6,3 z" className="graph-arrowhead" />
            </marker>
          </defs>

          <g
            className="graph-edges"
            fill="none"
            markerEnd="url(#workflow-arrow)"
          >
            <path d="M140 194H190" />
            <path d="M370 194H435" />
            <path d="M280 162V28H952V278" />
            <path d="M615 178C648 166 660 139 690 114" />
            <path d="M615 208C650 225 660 250 690 286" />
            <path d="M775 126V272" />
            <path d="M690 82C650 56 642 130 615 166" />
            <path d="M860 304H900" />
          </g>

          <g className="graph-branch-labels">
            <text x="458" y="46">
              blocked
            </text>
            <text x="633" y="151">
              approval required
            </text>
            <text x="632" y="251">
              no approval needed
            </text>
            <text x="792" y="203">
              approved
            </text>
            <text x="633" y="72">
              rejected
            </text>
          </g>

          <g className="graph-node graph-node-terminal">
            <rect x="36" y="168" width="104" height="52" rx="26" />
            <text x="88" y="199" textAnchor="middle">
              START
            </text>
          </g>
          <g className="graph-node">
            <rect x="190" y="162" width="180" height="64" rx="12" />
            <text x="280" y="190" textAnchor="middle">
              Input guardrail
            </text>
            <text
              x="280"
              y="207"
              textAnchor="middle"
              className="graph-node-caption"
            >
              Validate request
            </text>
          </g>
          <g className="graph-node graph-node-agent">
            <rect x="435" y="162" width="180" height="64" rx="12" />
            <text x="525" y="190" textAnchor="middle">
              Procurement agent
            </text>
            <text
              x="525"
              y="207"
              textAnchor="middle"
              className="graph-node-caption"
            >
              Prepare purchase
            </text>
          </g>
          <g className="graph-node graph-node-approval">
            <rect x="690" y="62" width="170" height="64" rx="12" />
            <text x="775" y="90" textAnchor="middle">
              Manager approval
            </text>
            <text
              x="775"
              y="107"
              textAnchor="middle"
              className="graph-node-caption"
            >
              Human review
            </text>
          </g>
          <g className="graph-node graph-node-output">
            <rect x="690" y="272" width="170" height="64" rx="12" />
            <text x="775" y="300" textAnchor="middle">
              Output guardrail
            </text>
            <text
              x="775"
              y="317"
              textAnchor="middle"
              className="graph-node-caption"
            >
              Validate and commit
            </text>
          </g>
          <g className="graph-node graph-node-terminal">
            <rect x="900" y="278" width="104" height="52" rx="26" />
            <text x="952" y="309" textAnchor="middle">
              END
            </text>
          </g>
        </svg>
      </div>
      <details className="graph-source">
        <summary>View Mermaid source</summary>
        {mermaidSource ? (
          <pre className="workflow-definition">
            <code>{definition}</code>
          </pre>
        ) : (
          <p className="muted-copy">No Mermaid definition available.</p>
        )}
      </details>
    </div>
  );
}
