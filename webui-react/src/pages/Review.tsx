import { useState } from 'react';

interface ReviewReport {
  target_date: string;
  generated_at: string;
  activities_count: number;
  new_memories: number;
  topics: string[];
  key_decisions: string[];
  knowledge_gaps: string[];
  connections: string[];
  actions: string[];
  narrative: string;
  token_usage?: Record<string, any>;
}

export default function Review() {
  const [date, setDate] = useState('');
  const [report, setReport] = useState<ReviewReport | null>(null);
  const [latestContent, setLatestContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const generateReview = async () => {
    setLoading(true);
    setLatestContent(null);
    try {
      const resp = await fetch('/api/v1/system/review', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(date ? { date } : {}),
      });
      const data = await resp.json();
      setReport(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const loadLatest = async () => {
    setLoading(true);
    setReport(null);
    try {
      const resp = await fetch('/api/v1/system/review/latest');
      const data = await resp.json();
      if (data.found) {
        setLatestContent(data.content);
      } else {
        setLatestContent('No review reports found.');
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Daily Review</h1>
        <div className="flex gap-2">
          <button className="btn btn-sm" style={{ background: '#374151', color: '#e1e2ea' }} onClick={loadLatest}>
            Load Latest
          </button>
        </div>
      </div>

      <div className="card mb-6">
        <div className="flex gap-3 items-end">
          <div className="flex-1">
            <label className="text-xs text-gray-400 block mb-1">Date (empty = yesterday)</label>
            <input
              type="date"
              value={date}
              onChange={e => setDate(e.target.value)}
              placeholder="YYYY-MM-DD"
            />
          </div>
          <button
            className="btn btn-primary"
            onClick={generateReview}
            disabled={loading}
          >
            {loading ? 'Generating...' : 'Generate Review'}
          </button>
        </div>
      </div>

      {/* Generated report */}
      {report && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="stat-card">
              <div className="value text-blue-400">{report.activities_count}</div>
              <div className="label">Activities</div>
            </div>
            <div className="stat-card">
              <div className="value text-green-400">{report.new_memories}</div>
              <div className="label">New Memories</div>
            </div>
          </div>

          {report.topics.length > 0 && (
            <div className="card">
              <h3 className="font-bold mb-2 text-sm">Topics</h3>
              <div className="flex flex-wrap gap-2">
                {report.topics.map((t, i) => (
                  <span key={i} className="badge badge-active">{t}</span>
                ))}
              </div>
            </div>
          )}

          {report.key_decisions.length > 0 && (
            <div className="card">
              <h3 className="font-bold mb-2 text-sm">Key Decisions</h3>
              <ul className="space-y-1">
                {report.key_decisions.map((d, i) => (
                  <li key={i} className="text-sm">- {d}</li>
                ))}
              </ul>
            </div>
          )}

          {report.knowledge_gaps.length > 0 && (
            <div className="card">
              <h3 className="font-bold mb-2 text-sm text-yellow-400">Knowledge Gaps</h3>
              <ul className="space-y-1">
                {report.knowledge_gaps.map((g, i) => (
                  <li key={i} className="text-sm">- {g}</li>
                ))}
              </ul>
            </div>
          )}

          {report.connections.length > 0 && (
            <div className="card">
              <h3 className="font-bold mb-2 text-sm">Connections</h3>
              <ul className="space-y-1">
                {report.connections.map((c, i) => (
                  <li key={i} className="text-sm">- {c}</li>
                ))}
              </ul>
            </div>
          )}

          {report.actions.length > 0 && (
            <div className="card">
              <h3 className="font-bold mb-2 text-sm text-blue-400">Suggested Actions</h3>
              <ul className="space-y-1">
                {report.actions.map((a, i) => (
                  <li key={i} className="text-sm">- {a}</li>
                ))}
              </ul>
            </div>
          )}

          {report.token_usage && (
            <div className="card">
              <h3 className="font-bold mb-2 text-sm">Token Usage</h3>
              <div className="text-sm text-gray-400">
                Total: {report.token_usage.total_input || 0} in + {report.token_usage.total_output || 0} out = {(report.token_usage.total_input || 0) + (report.token_usage.total_output || 0)}
              </div>
            </div>
          )}

          {report.narrative && (
            <div className="card">
              <h3 className="font-bold mb-2 text-sm">Narrative</h3>
              <p className="text-sm italic text-gray-300">{report.narrative}</p>
            </div>
          )}

          <p className="text-xs text-gray-600">Target: {report.target_date} | Generated: {report.generated_at}</p>
        </div>
      )}

      {/* Loaded latest markdown */}
      {latestContent && (
        <div className="card">
          <pre className="text-xs text-gray-300 whitespace-pre-wrap font-mono">{latestContent}</pre>
        </div>
      )}

      {!report && !latestContent && !loading && (
        <p className="text-gray-500 text-sm">Generate a review or load the latest one.</p>
      )}
    </div>
  );
}
