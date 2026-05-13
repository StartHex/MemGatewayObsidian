import { useState, useEffect } from 'react';

export default function Dashboard() {
  const [stats, setStats] = useState({ active: 0, fading: 0, total: 0, inbox_pending: 0 });
  const [alerts, setAlerts] = useState<{ level: string; content: string; file_exists: boolean } | null>(null);
  const [captureText, setCaptureText] = useState('');
  const [captureOutput, setCaptureOutput] = useState('');
  const [captureStatus, setCaptureStatus] = useState('');
  const [agentStatus, setAgentStatus] = useState('');

  const fetchStats = async () => {
    try {
      const [statsResp, alertsResp] = await Promise.all([
        fetch('/api/v1/system/stats'),
        fetch('/api/v1/system/alerts'),
      ]);
      setStats(await statsResp.json());
      setAlerts(await alertsResp.json());
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

      {/* Alerts panel */}
      {alerts && alerts.file_exists && alerts.level !== 'OK' && (
        <div className="card mb-4" style={{
          borderColor: alerts.level === 'CRITICAL' ? '#ef4444' : alerts.level === 'ACTION' ? '#eab308' : '#3b82f6',
          background: alerts.level === 'CRITICAL' ? 'rgba(239,68,68,0.08)' : alerts.level === 'ACTION' ? 'rgba(234,179,8,0.08)' : 'rgba(59,130,246,0.06)',
        }}>
          <div className="text-xs font-bold mb-1"
            style={{ color: alerts.level === 'CRITICAL' ? '#ef4444' : alerts.level === 'ACTION' ? '#eab308' : '#3b82f6' }}>
            ⚠️ 系统提醒 ({alerts.level})
          </div>
          <pre className="text-xs" style={{ color: '#9ca3af', whiteSpace: 'pre-wrap', margin: 0, background: 'transparent' }}>
            {alerts.content.replace(/^#.*\n/, '').trim()}
          </pre>
        </div>
      )}

      {/* Stats cards */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <div className="stat-card">
          <div className="value text-green-400">{stats.active}</div>
          <div className="label">活跃记忆</div>
        </div>
        <div className="stat-card">
          <div className="value text-yellow-400">{stats.fading}</div>
          <div className="label">衰减中</div>
        </div>
        <div className="stat-card">
          <div className="value text-blue-400">{stats.total}</div>
          <div className="label">全部记录</div>
        </div>
        <div className="stat-card">
          <div className="value text-purple-400">{stats.inbox_pending}</div>
          <div className="label">待处理</div>
        </div>
      </div>

      {/* Agent triggers */}
      <div className="card mb-6">
        <h2 className="text-sm font-bold mb-2">手动触发 Agent</h2>
        <div className="flex gap-2 flex-wrap">
          {[
            { key: 'consolidation', label: '巩固记忆' },
            { key: 'forgetting', label: '遗忘清理' },
            { key: 'meta_cognition', label: '健康检查' },
            { key: 'review', label: '每日复盘' },
            { key: 'supervisor', label: '系统巡检' },
          ].map(a => (
            <button
              key={a.key}
              className="btn btn-sm"
              style={{ background: '#374151', color: '#e1e2ea' }}
              onClick={() => triggerAgent(a.key)}
            >
              {a.label}
            </button>
          ))}
        </div>
        {agentStatus && <div className="text-xs mt-2 text-gray-400">{agentStatus}</div>}
      </div>

      {/* Quick Capture */}
      <div className="card">
        <h2 className="text-sm font-bold mb-3">快速记录</h2>
        <textarea
          className="mb-2"
          rows={2}
          placeholder="输入内容..."
          value={captureText}
          onChange={e => setCaptureText(e.target.value)}
        />
        <textarea
          className="mb-2"
          rows={2}
          placeholder="补充说明（可选）..."
          value={captureOutput}
          onChange={e => setCaptureOutput(e.target.value)}
        />
        <div className="flex justify-between items-center">
          <button className="btn btn-primary btn-sm" onClick={handleCapture}>
            保存
          </button>
          {captureStatus && <span className="text-xs text-gray-400">{captureStatus}</span>}
        </div>
      </div>
    </div>
  );
}
