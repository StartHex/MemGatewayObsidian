import { useState, useEffect } from 'react';

interface MemoryFull {
  id: string;
  type: string;
  status: string;
  title?: string;
  content: string;
  strength: number;
  importance: number;
  tags: string[];
  source?: string;
  context?: string;
  created?: string;
  last_retrieved?: string;
  retrieval_count?: number;
  file_path?: string;
  conflict?: boolean;
}

interface Props {
  memoryId: string;
  onClose: () => void;
}

const TYPE_LABELS: Record<string, string> = {
  raw_input: '对话',
  semantic: '记忆',
  episodic: '情景',
  procedural: '流程',
  working_slot: '工作区',
};

const STATUS_LABELS: Record<string, string> = {
  raw: '待处理',
  active: '活跃',
  fading: '衰减中',
  archived: '已归档',
  processing: '处理中',
};

export default function MemoryDetail({ memoryId, onClose }: Props) {
  const [mem, setMem] = useState<MemoryFull | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`/api/v1/memories/${memoryId}`)
      .then(r => r.json())
      .then(setMem)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [memoryId]);

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
        zIndex: 100, display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: 'var(--bg-card)', borderRadius: '12px',
          maxWidth: '720px', width: '90%', maxHeight: '85vh', overflow: 'auto',
          padding: '24px', border: '1px solid var(--border)',
        }}
      >
        {loading ? (
          <p style={{ color: 'var(--text-secondary)' }}>Loading...</p>
        ) : !mem ? (
          <p style={{ color: 'var(--text-secondary)' }}>Not found</p>
        ) : (
          <>
            {/* Header */}
            <div className="flex justify-between items-start mb-4">
              <div>
                <span style={{
                  fontSize: '11px', padding: '2px 8px', borderRadius: '4px',
                  background: mem.type === 'raw_input' ? '#1e40af20' : '#065f4620',
                  color: mem.type === 'raw_input' ? '#60a5fa' : '#34d399',
                }}>
                  {TYPE_LABELS[mem.type] || mem.type}
                </span>
                <span style={{
                  fontSize: '11px', padding: '2px 8px', borderRadius: '4px',
                  marginLeft: '8px',
                  background: mem.status === 'active' ? '#22c55e20' : '#6b728020',
                  color: mem.status === 'active' ? '#22c55e' : '#9ca3af',
                }}>
                  {STATUS_LABELS[mem.status] || mem.status}
                </span>
              </div>
              <button
                onClick={onClose}
                style={{
                  background: 'none', border: 'none', color: 'var(--text-secondary)',
                  fontSize: '20px', cursor: 'pointer', lineHeight: 1,
                }}
              >
                ✕
              </button>
            </div>

            {/* Title */}
            <h2 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '12px', color: 'var(--text-primary)' }}>
              {mem.title || mem.id}
            </h2>

            {/* Content */}
            <div style={{
              background: 'var(--bg-primary)', borderRadius: '8px',
              padding: '16px', marginBottom: '16px',
              whiteSpace: 'pre-wrap', fontSize: '14px',
              lineHeight: 1.7, color: 'var(--text-primary)',
              maxHeight: '360px', overflow: 'auto',
            }}>
              {mem.content || '(no content)'}
            </div>

            {/* Meta */}
            <div style={{
              display: 'grid', gridTemplateColumns: '1fr 1fr',
              gap: '6px 16px', fontSize: '13px', color: 'var(--text-secondary)',
            }}>
              <div>ID: <span style={{ fontFamily: 'monospace', fontSize: '11px' }}>{mem.id}</span></div>
              <div>强度: {mem.strength?.toFixed(0)}</div>
              <div>重要性: {mem.importance?.toFixed(0)}</div>
              <div>来源: {mem.source || '-'}</div>
              <div>检索次数: {mem.retrieval_count ?? 0}</div>
              {mem.conflict !== undefined && (
                <div style={{ color: mem.conflict ? 'var(--accent-red)' : 'var(--accent-green)' }}>
                  {mem.conflict ? '⚠ 冲突' : '✓ 无冲突'}
                </div>
              )}
            </div>

            {/* Tags */}
            {mem.tags && mem.tags.length > 0 && (
              <div style={{ marginTop: '12px', display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                {mem.tags.map(t => (
                  <span key={t} style={{
                    fontSize: '11px', padding: '2px 8px', borderRadius: '4px',
                    background: 'var(--bg-primary)', color: 'var(--text-secondary)',
                  }}>
                    {t}
                  </span>
                ))}
              </div>
            )}

            {/* Context */}
            {mem.context && (
              <div style={{ marginTop: '12px' }}>
                <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '4px' }}>上下文</div>
                <div style={{
                  background: 'var(--bg-primary)', borderRadius: '6px',
                  padding: '10px', fontSize: '13px', color: 'var(--text-secondary)',
                }}>
                  {mem.context}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
