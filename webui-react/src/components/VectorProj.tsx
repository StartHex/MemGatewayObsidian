import { useEffect, useRef, useState } from 'react';

interface ProjectionPoint {
  id: string;
  x: number;
  y: number;
  type: string;
  label: string;
}

export default function VectorProj() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [points, setPoints] = useState<ProjectionPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const chartRef = useRef<any>(null);

  useEffect(() => {
    fetch('/api/v1/canvas/projection')
      .then(r => r.json())
      .then(async data => {
        setPoints(data.points || []);

        const typeColors: Record<string, string> = {
          semantic: '#3b82f6',
          episodic: '#22c55e',
          procedural: '#a855f7',
        };

        const series = ['semantic', 'episodic', 'procedural'].map(type => ({
          name: type,
          type: 'scatter',
          data: (data.points || [])
            .filter((p: ProjectionPoint) => p.type === type)
            .map((p: ProjectionPoint) => [p.x, p.y, p.label || p.id.slice(-8)]),
          symbolSize: 6,
          itemStyle: { color: typeColors[type] || '#6b7280' },
        }));

        if (containerRef.current && (data.points || []).length > 0) {
          const echarts = (await import('echarts')).default;
          if (chartRef.current) chartRef.current.dispose();
          chartRef.current = echarts.init(containerRef.current, 'dark');
          chartRef.current.setOption({
            tooltip: { formatter: (p: any) => p.value?.[2] || '' },
            legend: { data: ['semantic', 'episodic', 'procedural'], textStyle: { color: '#9ca3af' } },
            xAxis: { type: 'value', show: false },
            yAxis: { type: 'value', show: false },
            series,
            grid: { top: 10, right: 10, bottom: 10, left: 10 },
          });
          window.addEventListener('resize', () => chartRef.current?.resize());
        }
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Vector Projection (UMAP 2D)</h1>
      {loading && <p className="text-gray-400 text-sm">Loading projection data...</p>}
      {points.length === 0 && !loading && (
        <p className="text-gray-500 text-sm">No projection data available. Run vector indexing first.</p>
      )}
      <div ref={containerRef} className="canvas-container" />
    </div>
  );
}
