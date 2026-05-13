import { useEffect, useRef, useState } from 'react';

interface HeatmapCell {
  memory_id: string;
  title: string;
  strength: number;
  status: string;
  importance: number;
}

export default function Heatmap() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [cells, setCells] = useState<HeatmapCell[]>([]);
  const [loading, setLoading] = useState(true);
  const chartRef = useRef<any>(null);

  useEffect(() => {
    fetch('/api/v1/canvas/heatmap')
      .then(r => r.json())
      .then(async data => {
        setCells(data.cells || []);
        const items = (data.cells || []).map((c: HeatmapCell) => ({
          name: c.title || c.memory_id.slice(-12),
          value: Math.max(1, c.strength || 10),
          itemStyle: {
            color: c.status === 'active' ? '#22c55e' : c.status === 'fading' ? '#eab308' : '#6b7280',
          },
        }));

        if (containerRef.current && items.length > 0) {
          const echarts = (await import('echarts')).default;
          if (chartRef.current) chartRef.current.dispose();
          chartRef.current = echarts.init(containerRef.current, 'dark');
          chartRef.current.setOption({
            tooltip: {},
            series: [{
              type: 'treemap',
              data: items,
              width: '100%',
              height: '100%',
              roam: false,
              label: { show: true, formatter: '{b}' },
            }],
          });
          window.addEventListener('resize', () => chartRef.current?.resize());
        }
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-bold">Strength Heatmap</h1>
        <div className="text-xs text-gray-400">{cells.length} memories</div>
      </div>
      {loading && <p className="text-gray-400 text-sm">Loading...</p>}
      <div ref={containerRef} className="canvas-container" />
    </div>
  );
}
