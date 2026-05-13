import { useState } from 'react';

interface SearchResult {
  memory_id: string;
  title: string;
  snippet: string;
  score: number;
  strategy: string;
  file_path: string;
}

const STRATEGIES = ['auto', 'vector', 'keyword', 'exact', 'graph', 'timeline', 'traceback'];

export default function Search() {
  const [query, setQuery] = useState('');
  const [strategy, setStrategy] = useState('vector');
  const [topK, setTopK] = useState(10);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  const doSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setSearched(true);
    try {
      const resp = await fetch('/api/v1/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, strategy, top_k: topK }),
      });
      setResults(await resp.json());
    } catch (e) {
      console.error(e);
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  const strategyColor = (s: string) => {
    switch (s) {
      case 'vector': return '#3b82f6';
      case 'keyword': return '#22c55e';
      case 'exact': return '#eab308';
      case 'graph': return '#a855f7';
      case 'timeline': return '#f97316';
      case 'traceback': return '#ec4899';
      default: return '#6b7280';
    }
  };

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Search</h1>

      {/* Search bar */}
      <div className="card mb-4">
        <div className="flex gap-2 mb-3">
          <input
            className="flex-1"
            placeholder="Search memories..."
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && doSearch()}
          />
          <button
            className="btn btn-primary"
            onClick={doSearch}
            disabled={loading}
          >
            {loading ? '...' : 'Search'}
          </button>
        </div>

        {/* Options */}
        <div className="flex gap-4 items-center">
          <div className="flex-1">
            <label className="text-xs text-gray-500 block mb-1">Strategy</label>
            <select value={strategy} onChange={e => setStrategy(e.target.value)}>
              {STRATEGIES.map(s => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500 block mb-1">Top-K</label>
            <input
              type="number"
              min={1}
              max={50}
              value={topK}
              onChange={e => setTopK(Number(e.target.value))}
              style={{ width: 80 }}
            />
          </div>
        </div>
      </div>

      {/* Results */}
      <div className="space-y-2">
        {results.map(r => (
          <div key={r.memory_id} className="card">
            <div className="flex justify-between items-start mb-2">
              <div className="flex-1">
                <span className="font-medium text-sm">{r.title || r.memory_id}</span>
                <span className="text-xs text-gray-500 font-mono ml-2">{r.memory_id.slice(-20)}</span>
              </div>
              <div className="flex gap-2 items-center">
                <span
                  className="text-xs px-2 py-0.5 rounded"
                  style={{ background: strategyColor(r.strategy) + '20', color: strategyColor(r.strategy) }}
                >
                  {r.strategy}
                </span>
                <span className="text-xs font-bold">{(r.score * 100).toFixed(0)}%</span>
              </div>
            </div>
            {r.snippet && (
              <p className="text-xs text-gray-400 mt-1">{r.snippet.slice(0, 250)}</p>
            )}
          </div>
        ))}
        {results.length === 0 && searched && !loading && (
          <p className="text-gray-500 text-sm py-8 text-center">No results found.</p>
        )}
      </div>
    </div>
  );
}
