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
  file_path?: string;
}

const TYPE_LABELS: Record<string, string> = {
  raw_input: '对话',
  semantic: '记忆',
  episodic: '情景',
  procedural: '流程',
  working_slot: '工作区',
};

const FILTERS = [
  { key: 'all', label: '全部' },
  { key: 'raw_input', label: '对话' },
  { key: 'semantic', label: '记忆' },
  { key: 'episodic', label: '情景' },
];

const PAGE_SIZES = [10, 20, 50, 100];

export default function Browse() {
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(20);
  const [detailId, setDetailId] = useState<string | null>(null);

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

  const totalPages = Math.ceil(filtered.length / pageSize);
  const pageItems = filtered.slice(page * pageSize, (page + 1) * pageSize);

  // Reset to page 0 when filter/search/pageSize changes
  const setFilter = (key: string) => { setTypeFilter(key); setPage(0); };
  const setSearch = (q: string) => { setQuery(q); setPage(0); };
  const setSize = (n: number) => { setPageSize(n); setPage(0); };

  const pageNumbers = (): number[] => {
    const pages: number[] = [];
    const start = Math.max(0, page - 2);
    const end = Math.min(totalPages - 1, page + 2);
    for (let i = start; i <= end; i++) pages.push(i);
    return pages;
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
          {loading ? '加载中...' : '刷新'}
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
              onClick={() => setFilter(f.key)}
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
          onChange={e => setSearch(e.target.value)}
          style={{ width: '100%' }}
        />
      </div>

      {/* Pagination top */}
      <div className="flex justify-between items-center mb-2">
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">
            共 {filtered.length} 条
            {query && ` — 搜索: "${query}"`}
          </span>
          <select
            value={pageSize}
            onChange={e => setSize(Number(e.target.value))}
            style={{ fontSize: '11px', padding: '2px 6px', width: 'auto' }}
          >
            {PAGE_SIZES.map(n => (
              <option key={n} value={n}>{n}条/页</option>
            ))}
          </select>
        </div>
        {totalPages > 1 && (
          <div className="flex items-center gap-1">
            <button className="btn btn-sm" style={{ background: '#374151', color: '#e1e2ea' }}
              disabled={page === 0} onClick={() => setPage(0)}>«</button>
            <button className="btn btn-sm" style={{ background: '#374151', color: '#e1e2ea' }}
              disabled={page === 0} onClick={() => setPage(p => p - 1)}>‹</button>
            {pageNumbers().map(i => (
              <button
                key={i}
                className="btn btn-sm"
                onClick={() => setPage(i)}
                style={{
                  background: page === i ? '#3b82f6' : '#374151',
                  color: page === i ? '#fff' : '#e1e2ea',
                  minWidth: '32px',
                }}
              >
                {i + 1}
              </button>
            ))}
            <button className="btn btn-sm" style={{ background: '#374151', color: '#e1e2ea' }}
              disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)}>›</button>
            <button className="btn btn-sm" style={{ background: '#374151', color: '#e1e2ea' }}
              disabled={page >= totalPages - 1} onClick={() => setPage(totalPages - 1)}>»</button>
          </div>
        )}
      </div>

      {/* Results */}
      <div className="card">
        {loading ? (
          <p className="text-gray-500 text-sm py-8 text-center">加载中...</p>
        ) : pageItems.length === 0 ? (
          <p className="text-gray-500 text-sm py-8 text-center">
            {memories.length === 0 ? '暂无记录，开始对话即可自动记录。' : '无匹配结果。'}
          </p>
        ) : (
          <div className="space-y-1">
            {pageItems.map(m => (
              <div
                key={m.id}
                onClick={() => setDetailId(m.id)}
                className="flex items-start gap-3 py-2 border-b border-gray-800 last:border-0"
                style={{ cursor: 'pointer' }}
              >
                <span style={{
                  display: 'inline-block', fontSize: '11px', padding: '1px 6px',
                  borderRadius: '4px', flexShrink: 0, marginTop: '1px',
                  background: m.type === 'raw_input' ? '#1e40af20' : '#065f4620',
                  color: m.type === 'raw_input' ? '#60a5fa' : '#34d399',
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
                        <span key={t} className="text-xs px-1.5 py-0 rounded"
                          style={{ background: '#1f2937', color: '#6b7280' }}>{t}</span>
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

      {/* Pagination bottom */}
      {totalPages > 1 && (
        <div className="flex justify-center items-center gap-1 mt-3">
          <button className="btn btn-sm" style={{ background: '#374151', color: '#e1e2ea' }}
            disabled={page === 0} onClick={() => setPage(0)}>«</button>
          <button className="btn btn-sm" style={{ background: '#374151', color: '#e1e2ea' }}
            disabled={page === 0} onClick={() => setPage(p => p - 1)}>‹</button>
          {pageNumbers().map(i => (
            <button
              key={i} className="btn btn-sm"
              onClick={() => setPage(i)}
              style={{
                background: page === i ? '#3b82f6' : '#374151',
                color: page === i ? '#fff' : '#e1e2ea',
                minWidth: '32px',
              }}
            >{i + 1}</button>
          ))}
          <button className="btn btn-sm" style={{ background: '#374151', color: '#e1e2ea' }}
            disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)}>›</button>
          <button className="btn btn-sm" style={{ background: '#374151', color: '#e1e2ea' }}
            disabled={page >= totalPages - 1} onClick={() => setPage(totalPages - 1)}>»</button>
        </div>
      )}

      {detailId && <MemoryDetail memoryId={detailId} onClose={() => setDetailId(null)} />}
    </div>
  );
}
