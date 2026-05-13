import { useEffect, useRef, useState } from 'react';

interface TimelineEntry {
  date: string;
  count: number;
  memories: any[];
}

export default function Timeline() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [entries, setEntries] = useState<TimelineEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const chartRef = useRef<any>(null);

  useEffect(() => {
    fetch('/api/v1/canvas/timeline')
      .then(r => r.json())
      .then(async data => {
        setEntries(data.entries || []);
        const items = (data.entries || []).map((e: TimelineEntry) => ({
          name: e.date,
          value: [e.date, e.count],
        }));

        if (containerRef.current && items.length > 0) {
          const echarts = (await import('echarts')).default;
          if (chartRef.current) chartRef.current.dispose();
          chartRef.current = echarts.init(containerRef.current, 'dark');
          chartRef.current.setOption({
            tooltip: { trigger: 'item' },
            xAxis: { type: 'time', axisLabel: { color: '#9ca3af', fontSize: 10 } },
            yAxis: { type: 'value', axisLabel: { color: '#9ca3af' } },
            series: [{
              type: 'scatter',
              data: items,
              symbolSize: (val: number[]) => Math.max(8, Math.min(40, val[1] * 4)),
              itemStyle: { color: '#3b82f6' },
            }],
            grid: { top: 20, right: 20, bottom: 40, left: 50 },
          });
          window.addEventListener('resize', () => chartRef.current?.resize());
        }
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Episodic Timeline</h1>
      {loading && <p className="text-gray-400 text-sm">Loading...</p>}
      {entries.length === 0 && !loading && (
        <p className="text-gray-500 text-sm">No timeline data available.</p>
      )}
      <div ref={containerRef} className="canvas-container" />
    </div>
  );
}
