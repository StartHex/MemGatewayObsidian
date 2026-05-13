import { useState, useEffect } from 'react';

interface MemoryItem {
  id: string;
  title: string;
  type: string;
  status: string;
  strength: number;
  importance: number;
  tags: string[];
  file_path?: string;
}

const TYPE_LABELS: Record<string, string> = {
  raw_input: '对话',
  semantic: '记忆',
  episodic: '情景',
  procedural: '流程',
  working_slot: '工作区',
};

const TYPE_ORDER: Record<string, number> = {
  raw_input: 0,
  semantic: 1,
  episodic: 2,
  procedural: 3,
  working_slot: 4,
};

const FILTERS = [
  { key: 'all', label: '全部' },
  { key: 'raw_input', label: '对话' },
  { key: 'semantic', label: '记忆' },
  { key: 'episodic', label: '情景' },
];

export default function Browse() {
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 30;

  const fetchAll = async () => {
    setLoading(true);
    try {
      const resp = await fetch('/api/v1/memories?limit=200&sort_by=recent');
      const data = await resp.json();
      setMemories(data.items || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchAll(); }, []);

  const filtered = memories.filter(m => {
    if (typeFilter !== 'all' && m.type !== typeFilter) return false;
    if (!query.trim()) return true;
    const q = query.toLowerCase();
    return (
      (m.title || '').toLowerCase().includes(q) ||
      m.id.toLowerCase().includes(q) ||
      (m.tags || []).some(t => t.toLowerCase().includes(q))
    );
  });

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const pageItems = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const typeBadgeClass = (type: string) => {
    switch (type) {
      case 'raw_input': return 'badge' + ' ' + 'text-xs px-2 py-0.5 rounded';
      case 'semantic': return 'badge' + ' ' + 'text-xs px-2 py-0.5 rounded';
      default: return 'badge' + ' ' + 'text-xs px-2 py-0.5 rounded';
    }
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-bold">Memories</h1>
        <button
          className="btn btn-sm"
          style={{ background: '#374151', color: '#e1e2ea' }}
          onClick={fetchAll}
          disabled={loading}
        >
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {/* Type filter tabs */}
      <div className="flex gap-2 mb-3">
        {FILTERS.map(f => {
          const count = f.key === 'all'
            ? memories.length
            : memories.filter(m => m.type === f.key).length;
          return (
            <button
              key={f.key}
              className="btn btn-sm"
              onClick={() => { setTypeFilter(f.key); setPage(0); }}
              style={{
                background: typeFilter === f.key ? '#3b82f6' : '#1f2937',
                color: typeFilter === f.key ? '#fff' : '#9ca3af',
                border: '1px solid #374151',
              }}
            >
              {f.label}
              <span className="ml-1 text-xs opacity-60">({count})</span>
            </button>
          );
        })}
      </div>

      {/* Search bar */}
      <div className="card mb-3">
        <input
          placeholder="搜索记忆..."
          value={query}
          onChange={e => { setQuery(e.target.value); setPage(0); }}
          style={{ width: '100%' }}
        />
      </div>

      {/* Results */}
      <div className="card">
        <div className="flex justify-between items-center mb-2">
          <span className="text-xs text-gray-500">
            {filtered.length} results
            {query && ` for "${query}"`}
          </span>
          {totalPages > 1 && (
            <div className="flex gap-1">
              <button
                className="btn btn-sm"
                style={{ background: '#374151', color: '#e1e2ea' }}
                disabled={page === 0}
                onClick={() => setPage(p => p - 1)}
              >
                Prev
              </button>
              <span className="text-xs text-gray-500 self-center px-2">
                {page + 1}/{totalPages}
              </span>
              <button
                className="btn btn-sm"
                style={{ background: '#374151', color: '#e1e2ea' }}
                disabled={page >= totalPages - 1}
                onClick={() => setPage(p => p + 1)}
              >
                Next
              </button>
            </div>
          )}
        </div>

        {loading ? (
          <p className="text-gray-500 text-sm py-8 text-center">Loading...</p>
        ) : pageItems.length === 0 ? (
          <p className="text-gray-500 text-sm py-8 text-center">
            {memories.length === 0 ? 'No memories yet. Start a conversation to build your memory vault.' : 'No matches.'}
          </p>
        ) : (
          <div className="space-y-1">
            {pageItems.map(m => (
              <div
                key={m.id}
                className="flex items-start gap-3 py-2 border-b border-gray-800 last:border-0"
              >
                <span style={{
                  display: 'inline-block',
                  fontSize: '11px',
                  padding: '1px 6px',
                  borderRadius: '4px',
                  background: m.type === 'raw_input' ? '#1e40af20' : '#065f4620',
                  color: m.type === 'raw_input' ? '#60a5fa' : '#34d399',
                  whiteSpace: 'nowrap',
                  flexShrink: 0,
                  marginTop: '1px',
                }}>
                  {TYPE_LABELS[m.type] || m.type}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="text-sm truncate" style={{ color: '#e1e2ea' }}>
                    {(m.title || m.id).slice(0, 120)}
                  </div>
                  {m.tags && m.tags.length > 0 && (
                    <div className="flex gap-1 mt-1 flex-wrap">
                      {m.tags.slice(0, 5).map(t => (
                        <span key={t} className="text-xs px-1.5 py-0 rounded" style={{ background: '#1f2937', color: '#6b7280' }}>
                          {t}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <span className="text-xs text-gray-600 font-mono flex-shrink-0" style={{ marginTop: '2px' }}>
                  {m.id.slice(-12)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
