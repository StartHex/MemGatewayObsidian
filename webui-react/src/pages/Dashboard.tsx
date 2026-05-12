import { useState, useEffect } from 'react';

export default function Dashboard() {
  const [stats, setStats] = useState({ active: 0, fading: 0, total: 0 });
  const [captureText, setCaptureText] = useState('');

  useEffect(() => {
    fetch('/api/v1/system/stats').then(r => r.json()).then(setStats);
  }, []);

  const handleCapture = async () => {
    if (!captureText.trim()) return;
    await fetch('/api/v1/memories', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: captureText, type: 'raw_input', source: 'webui' }),
    });
    setCaptureText('');
  };

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Dashboard</h1>
      <div className="grid grid-cols-3 gap-4 mb-8">
        <div className="bg-gray-800 rounded p-4">
          <div className="text-3xl font-bold text-green-400">{stats.active}</div>
          <div className="text-sm text-gray-400">Active Memories</div>
        </div>
        <div className="bg-gray-800 rounded p-4">
          <div className="text-3xl font-bold text-yellow-400">{stats.fading}</div>
          <div className="text-sm text-gray-400">Fading</div>
        </div>
        <div className="bg-gray-800 rounded p-4">
          <div className="text-3xl font-bold text-blue-400">{stats.total}</div>
          <div className="text-sm text-gray-400">Total</div>
        </div>
      </div>

      <div className="bg-gray-800 rounded p-4">
        <h2 className="text-lg mb-2">Quick Capture</h2>
        <textarea
          className="w-full bg-gray-700 rounded p-2 text-sm"
          rows={3}
          placeholder="记录你的想法..."
          value={captureText}
          onChange={e => setCaptureText(e.target.value)}
        />
        <button
          className="mt-2 bg-blue-600 hover:bg-blue-700 px-4 py-1 rounded text-sm"
          onClick={handleCapture}
        >
          Save
        </button>
      </div>
    </div>
  );
}
