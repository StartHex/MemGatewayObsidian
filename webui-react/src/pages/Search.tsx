import { useState } from 'react';

interface SearchResult {
  memory_id: string;
  title: string;
  snippet: string;
  score: number;
  strategy: string;
}

export default function Search() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);

  const doSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const resp = await fetch('/api/v1/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, strategy: 'vector', top_k: 10 }),
      });
      setResults(await resp.json());
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Search</h1>
      <div className="flex gap-2 mb-6">
        <input
          className="flex-1 bg-gray-800 rounded px-3 py-2 text-sm"
          placeholder="搜索记忆..."
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && doSearch()}
        />
        <button
          className="bg-blue-600 hover:bg-blue-700 px-4 py-1 rounded text-sm"
          onClick={doSearch}
          disabled={loading}
        >
          {loading ? '...' : 'Search'}
        </button>
      </div>

      <div className="space-y-2">
        {results.map(r => (
          <div key={r.memory_id} className="bg-gray-800 rounded p-3">
            <div className="flex justify-between items-start mb-1">
              <span className="font-medium text-sm">{r.title || r.memory_id}</span>
              <span className="text-xs text-gray-500">{r.strategy} · {r.score.toFixed(2)}</span>
            </div>
            {r.snippet && <p className="text-xs text-gray-400">{r.snippet.slice(0, 200)}</p>}
          </div>
        ))}
        {results.length === 0 && !loading && query && (
          <p className="text-gray-500 text-sm">无结果</p>
        )}
      </div>
    </div>
  );
}
