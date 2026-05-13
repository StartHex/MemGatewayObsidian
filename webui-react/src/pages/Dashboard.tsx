import { useState, useEffect } from 'react';
import MemoryDetail from '../components/MemoryDetail';

interface MemoryItem {
  id: string;
  title: string;
  type: string;
  status: string;
  strength: number;
  importance: number;
  tags: string[];
}

const TYPE_LABELS: Record<string, string> = {
  raw_input: '对话',
  semantic: '记忆',
  episodic: '情景',
  procedural: '流程',
  working_slot: '工作区',
};

export default function Dashboard() {
  const [stats, setStats] = useState({ active: 0, fading: 0, total: 0, inbox_pending: 0 });
  const [recent, setRecent] = useState<MemoryItem[]>([]);
  const [captureText, setCaptureText] = useState('');
  const [captureOutput, setCaptureOutput] = useState('');
  const [captureStatus, setCaptureStatus] = useState('');
  const [agentStatus, setAgentStatus] = useState('');
  const [detailId, setDetailId] = useState<string | null>(null);

  const fetchStats = async () => {
    try {
      const [statsResp, memsResp] = await Promise.all([
        fetch('/api/v1/system/stats'),
        fetch('/api/v1/memories?limit=20&sort_by=recent'),
      ]);
      setStats(await statsResp.json());
      const mems = await memsResp.json();
      setRecent(mems.items || []);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => { fetchStats(); }, []);

  const handleCapture = async () => {
    if (!captureText.trim()) return;
    setCaptureStatus('Saving...');
    try {
      await fetch('/api/v1/memories', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content: captureText,
          type: 'raw_input',
          source: 'webui',
          importance: 60,
          output: captureOutput.trim() || undefined,
        }),
      });
      setCaptureText('');
      setCaptureOutput('');
      setCaptureStatus('Saved!');
      fetchStats();
      setTimeout(() => setCaptureStatus(''), 2000);
    } catch (e) {
      setCaptureStatus(`Error: ${e}`);
    }
  };

  const triggerAgent = async (agent: string) => {
    setAgentStatus(`Triggering ${agent}...`);
    try {
      await fetch('/api/v1/system/agents/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent }),
      });
      setAgentStatus(`${agent} completed.`);
      fetchStats();
      setTimeout(() => setAgentStatus(''), 3000);
    } catch (e) {
      setAgentStatus(`Error: ${e}`);
    }
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <button className="btn btn-sm" style={{ background: '#374151', color: '#e1e2ea' }} onClick={fetchStats}>
          Refresh
        </button>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <div className="stat-card">
          <div className="value text-green-400">{stats.active}</div>
          <div className="label">Active</div>
        </div>
        <div className="stat-card">
          <div className="value text-yellow-400">{stats.fading}</div>
          <div className="label">Fading</div>
        </div>
        <div className="stat-card">
          <div className="value text-blue-400">{stats.total}</div>
          <div className="label">Total</div>
        </div>
        <div className="stat-card">
          <div className="value text-purple-400">{stats.inbox_pending}</div>
          <div className="label">Inbox Pending</div>
        </div>
      </div>

      {/* Agent triggers */}
      <div className="card mb-6">
        <h2 className="text-sm font-bold mb-2">Agent Triggers</h2>
        <div className="flex gap-2 flex-wrap">
          {['consolidation', 'forgetting', 'meta_cognition', 'review'].map(a => (
            <button
              key={a}
              className="btn btn-sm"
              style={{ background: '#374151', color: '#e1e2ea' }}
              onClick={() => triggerAgent(a)}
            >
              {a.replace('_', ' ')}
            </button>
          ))}
        </div>
        {agentStatus && <div className="text-xs mt-2 text-gray-400">{agentStatus}</div>}
      </div>

      {/* Quick Capture */}
      <div className="card mb-6">
        <h2 className="text-sm font-bold mb-3">Quick Capture</h2>
        <textarea
          className="mb-2"
          rows={2}
          placeholder="Question / thought..."
          value={captureText}
          onChange={e => setCaptureText(e.target.value)}
        />
        <textarea
          className="mb-2"
          rows={2}
          placeholder="Answer / output (optional)..."
          value={captureOutput}
          onChange={e => setCaptureOutput(e.target.value)}
        />
        <div className="flex justify-between items-center">
          <button className="btn btn-primary btn-sm" onClick={handleCapture}>
            Save
          </button>
          {captureStatus && <span className="text-xs text-gray-400">{captureStatus}</span>}
        </div>
      </div>

      {/* Recent memories */}
      <div className="card">
        <h2 className="text-sm font-bold mb-2">Recent Memories</h2>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Type</th>
              <th>Title</th>
              <th>Strength</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {recent.length === 0 && (
              <tr><td colSpan={5} className="text-center text-gray-500 py-4">No memories yet</td></tr>
            )}
            {recent.map(m => (
              <tr key={m.id} onClick={() => setDetailId(m.id)} style={{ cursor: 'pointer' }}>
                <td className="font-mono text-xs">{m.id.slice(-16)}</td>
                <td><span className="badge badge-active">{TYPE_LABELS[m.type] || m.type}</span></td>
                <td>{m.title || m.id}</td>
                <td>{m.strength.toFixed(0)}</td>
                <td>
                  <span className={`badge badge-${m.status === 'active' ? 'active' : m.status === 'fading' ? 'fading' : 'archived'}`}>
                    {m.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {detailId && <MemoryDetail memoryId={detailId} onClose={() => setDetailId(null)} />}
    </div>
  );
}
