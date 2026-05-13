import { useEffect, useRef, useState } from 'react';

interface TimelineBucket {
  date: string;
  count: number;
  items: { id: string; title: string; tags: string[] }[];
}

export default function Timeline() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [buckets, setBuckets] = useState<TimelineBucket[]>([]);
  const [loading, setLoading] = useState(true);
  const chartRef = useRef<any>(null);

  useEffect(() => {
    fetch('/api/v1/canvas/timeline')
      .then(r => r.json())
      .then(async data => {
        const raw = data.buckets || [];
        setBuckets(raw);

        // Filter out non-date buckets (review-*, etc.)
        const dateBuckets = raw.filter((b: TimelineBucket) => /^\d{4}-\d{2}-\d{2}$/.test(b.date));
        const items = dateBuckets.map((b: TimelineBucket) => ({
          name: b.date,
          value: [b.date, b.count],
        }));

        if (containerRef.current && items.length > 0) {
          const echartsLib = await import('echarts');
          const echarts = (echartsLib as any).init ? echartsLib : (echartsLib as any).default;
          if (chartRef.current) chartRef.current.dispose();
          chartRef.current = echarts.init(containerRef.current, 'dark');
          chartRef.current.setOption({
            tooltip: {
              trigger: 'item',
              formatter: (p: any) => `${p.value[0]}<br/>Memories: ${p.value[1]}`,
            },
            xAxis: { type: 'time', axisLabel: { color: '#9ca3af', fontSize: 10 } },
            yAxis: { type: 'value', axisLabel: { color: '#9ca3af' }, name: 'Count' },
            series: [{
              type: 'scatter',
              data: items,
              symbolSize: (val: number[]) => Math.max(12, Math.min(48, val[1] * 12)),
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
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-bold">Episodic Timeline</h1>
        <div className="text-xs text-gray-400">{buckets.length} days</div>
      </div>
      {loading && <p className="text-gray-400 text-sm">Loading...</p>}
      {buckets.length === 0 && !loading && (
        <p className="text-gray-500 text-sm">No timeline data available.</p>
      )}
      <div ref={containerRef} className="canvas-container" />
      {/* Day list below chart */}
      {buckets.length > 0 && (
        <div className="mt-4 space-y-1">
          {buckets.filter(b => /^\d{4}-\d{2}-\d{2}$/.test(b.date)).map(b => (
            <div key={b.date} className="card flex justify-between items-center">
              <span className="text-sm font-medium">{b.date}</span>
              <span className="badge badge-active">{b.count} entries</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
