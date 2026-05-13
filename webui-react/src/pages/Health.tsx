import { useState, useEffect } from 'react';

interface HealthData {
  generated_at: string;
  inbox_pending: number;
  active_count: number;
  fading_count: number;
  archived_count: number;
  strength_distribution: Record<string, number>;
  orphan_count: number;
  vector_inconsistencies: number;
  conflict_count: number;
  knowledge_gaps: string[];
  recommendations: string[];
}

export function HealthReport() {
  const [data, setData] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchHealth = async () => {
    setLoading(true);
    try {
      const resp = await fetch('/api/v1/system/health');
      setData(await resp.json());
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchHealth(); }, []);

  if (loading) return <p className="text-gray-400 text-sm">Loading...</p>;
  if (!data) return <p className="text-red-400 text-sm">Failed to load health report.</p>;

  const total = data.active_count + data.fading_count + data.archived_count || 1;

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">System Health</h1>
        <button className="btn btn-primary btn-sm" onClick={fetchHealth}>Refresh</button>
      </div>

      <div className="grid grid-cols-4 gap-4 mb-6">
        <div className="stat-card">
          <div className="value text-blue-400">{data.inbox_pending}</div>
          <div className="label">Inbox Pending</div>
        </div>
        <div className="stat-card">
          <div className="value text-green-400">{data.active_count}</div>
          <div className="label">Active</div>
        </div>
        <div className="stat-card">
          <div className="value text-yellow-400">{data.fading_count}</div>
          <div className="label">Fading</div>
        </div>
        <div className="stat-card">
          <div className="value text-red-400">{data.conflict_count}</div>
          <div className="label">Conflicts</div>
        </div>
      </div>

      {/* Strength Distribution */}
      <div className="card mb-6">
        <h2 className="text-lg font-bold mb-3">Strength Distribution</h2>
        <div className="flex gap-4">
          {Object.entries(data.strength_distribution).map(([k, v]) => (
            <div key={k} className="flex-1">
              <div className="text-xs text-gray-400 uppercase mb-1">{k}</div>
              <div className="flex items-end gap-2">
                <div className="text-xl font-bold">{v}</div>
                <div className="text-xs text-gray-500">({(v / total * 100).toFixed(1)}%)</div>
              </div>
              <div className="mt-2 h-2 bg-gray-800 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${(v / total * 100)}%`,
                    backgroundColor: k === 'strong' ? '#22c55e' : k === 'healthy' ? '#3b82f6' : k === 'fading' ? '#eab308' : '#ef4444',
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Orphans & Inconsistencies */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        <div className="card">
          <div className="text-sm text-gray-400">Orphan Nodes</div>
          <div className="text-2xl font-bold mt-1">{data.orphan_count}</div>
        </div>
        <div className="card">
          <div className="text-sm text-gray-400">Vector Inconsistencies</div>
          <div className="text-2xl font-bold mt-1">{data.vector_inconsistencies}</div>
        </div>
      </div>

      {/* Knowledge Gaps */}
      {data.knowledge_gaps.length > 0 && (
        <div className="card mb-6">
          <h2 className="text-lg font-bold text-yellow-400 mb-2">Knowledge Gaps</h2>
          <ul className="space-y-1">
            {data.knowledge_gaps.map((g, i) => (
              <li key={i} className="text-sm text-gray-300">- {g}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Recommendations */}
      {data.recommendations.length > 0 && (
        <div className="card">
          <h2 className="text-lg font-bold text-blue-400 mb-2">Recommendations</h2>
          <ul className="space-y-1">
            {data.recommendations.map((r, i) => (
              <li key={i} className="text-sm text-gray-300">- {r}</li>
            ))}
          </ul>
        </div>
      )}

      {data.generated_at && (
        <p className="text-xs text-gray-600 mt-4">Generated: {data.generated_at}</p>
      )}
    </div>
  );
}
