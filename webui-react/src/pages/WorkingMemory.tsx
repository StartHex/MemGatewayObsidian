import { useState, useEffect } from 'react';

interface Slot {
  slot_id: number;
  slot_name: string;
  memory_id: string;
  pinned: boolean;
  importance: number;
  operation_count: number;
}

export default function WorkingMemory() {
  const [slots, setSlots] = useState<Slot[]>([]);
  const [status, setStatus] = useState('');
  const [showPromote, setShowPromote] = useState(false);
  const [promoteId, setPromoteId] = useState('');
  const [promoteName, setPromoteName] = useState('');

  const fetchSlots = async () => {
    try {
      const resp = await fetch('/api/v1/working-memory/list', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      const data = await resp.json();
      setSlots(Array.isArray(data) ? data : []);
    } catch (e) {
      setStatus(`Error: ${e}`);
    }
  };

  useEffect(() => { fetchSlots(); }, []);

  const doAction = async (action: string, body: Record<string, any> = {}) => {
    try {
      const resp = await fetch(`/api/v1/working-memory/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await resp.json();
      if (resp.ok) {
        setStatus(`[${action}] OK`);
        fetchSlots();
      } else {
        setStatus(`[${action}] ${JSON.stringify(data)}`);
      }
    } catch (e) {
      setStatus(`[${action}] Error: ${e}`);
    }
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-bold">Working Memory</h1>
        <div className="flex gap-2">
          <button className="btn btn-primary btn-sm" onClick={() => setShowPromote(!showPromote)}>
            {showPromote ? 'Cancel' : '+ Promote'}
          </button>
          <button className="btn btn-sm" style={{ background: '#374151', color: '#e1e2ea' }} onClick={fetchSlots}>
            Refresh
          </button>
        </div>
      </div>

      {status && (
        <div className="mb-3 text-xs px-3 py-2 rounded bg-gray-800">{status}</div>
      )}

      {showPromote && (
        <div className="card mb-4">
          <h3 className="font-bold mb-2 text-sm">Promote to Working Memory</h3>
          <div className="flex gap-3 mb-2">
            <input
              placeholder="Memory ID"
              value={promoteId}
              onChange={e => setPromoteId(e.target.value)}
              className="flex-1"
            />
            <input
              placeholder="Slot name"
              value={promoteName}
              onChange={e => setPromoteName(e.target.value)}
              className="flex-1"
            />
          </div>
          <button
            className="btn btn-primary btn-sm"
            onClick={() => {
              doAction('promote', { memory_id: promoteId, name: promoteName || 'untitled' });
              setShowPromote(false);
              setPromoteId('');
              setPromoteName('');
            }}
          >
            Promote
          </button>
        </div>
      )}

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Slot</th>
              <th>Name</th>
              <th>Memory ID</th>
              <th>Pinned</th>
              <th>Ops</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {slots.length === 0 && (
              <tr><td colSpan={6} className="text-center text-gray-500 py-4">No active slots</td></tr>
            )}
            {slots.map(s => (
              <tr key={s.slot_id}>
                <td className="font-mono text-xs">{s.slot_id}</td>
                <td>{s.slot_name}</td>
                <td className="font-mono text-xs text-gray-400">{s.memory_id.slice(-16)}</td>
                <td>{s.pinned ? 'Y' : 'N'}</td>
                <td>{s.operation_count}</td>
                <td>
                  <div className="flex gap-1">
                    <button
                      className="btn btn-primary btn-sm"
                      onClick={() => doAction('update', { slot_id: s.slot_id, content: '# Updated\n\nContent from WebUI' })}
                    >
                      Update
                    </button>
                    <button
                      className="btn btn-warning btn-sm"
                      onClick={() => doAction('conclude', { slot_id: s.slot_id })}
                    >
                      Conclude
                    </button>
                    <button
                      className="btn btn-danger btn-sm"
                      onClick={() => doAction('evict', { slot_id: s.slot_id })}
                    >
                      Evict
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
