import { useEffect, useRef, useState } from 'react';

interface GraphNode {
  id: string;
  label: string;
  strength: number;
  status: string;
}

interface GraphEdge {
  source: string;
  target: string;
}

export default function MemoryGraph() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [nodeCount, setNodeCount] = useState(0);
  const [edgeCount, setEdgeCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const networkRef = useRef<any>(null);

  useEffect(() => {
    fetch('/api/v1/canvas/graph')
      .then(r => r.json())
      .then(async (data) => {
        const nodes = (data.nodes || []).map((n: GraphNode) => ({
          id: n.id,
          label: n.label || n.id.slice(-12),
          value: Math.max(5, (n.strength || 50) / 10),
          color: {
            background: n.status === 'active' ? '#22c55e' : n.status === 'fading' ? '#eab308' : '#6b7280',
            border: '#1a1b23',
          },
          font: { size: 10, color: '#9ca3af' },
        }));
        const edges = (data.edges || []).map((e: GraphEdge) => ({
          from: e.source,
          to: e.target,
          color: { color: '#2d2e3a', opacity: 0.5 },
        }));
        setNodeCount(nodes.length);
        setEdgeCount(edges.length);

        if (containerRef.current && nodes.length > 0) {
          const { Network } = await import('vis-network/standalone');
          if (networkRef.current) {
            networkRef.current.destroy();
          }
          networkRef.current = new Network(
            containerRef.current,
            { nodes, edges },
            {
              physics: { solver: 'forceAtlas2Based' },
              interaction: { hover: true, zoomView: true },
            },
          );
        }
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-bold">Memory Graph</h1>
        <div className="flex gap-4 text-xs text-gray-400">
          <span>Nodes: {nodeCount}</span>
          <span>Edges: {edgeCount}</span>
        </div>
      </div>
      {loading && <p className="text-gray-400 text-sm">Loading graph data...</p>}
      <div ref={containerRef} className="canvas-container" />
    </div>
  );
}
