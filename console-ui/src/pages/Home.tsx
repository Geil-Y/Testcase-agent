import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { listRequirements, importRequirements } from '../api/requirements';
import type { Requirement } from '../api/types';

function statusBadge(s: string) {
  if (s === 'reviewed') return <span className="badge badge-done">Reviewed</span>;
  if (s === 'pending') return <span className="badge badge-pending">Pending</span>;
  return <span className="badge badge-new">New</span>;
}

export default function Home() {
  const [reqs, setReqs] = useState<Requirement[]>([]);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [perPage] = useState(50);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [importing, setImporting] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  const totalPages = Math.max(1, Math.ceil(total / perPage));

  const fetchReqs = useCallback(async () => {
    try {
      setError('');
      const data = await listRequirements({
        q: q || undefined,
        status: status || undefined,
        offset: (page - 1) * perPage,
        limit: perPage,
      });
      setReqs(data.items);
      setTotal(data.total);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [q, status, page, perPage]);

  useEffect(() => { fetchReqs(); }, [fetchReqs]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === '/' && document.activeElement === document.body) {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    try {
      const result = await importRequirements(file);
      setError('');
      alert(`Imported ${result.imported} of ${result.total_rows} requirements`);
      await fetchReqs();
    } catch (err) {
      alert('Import failed: ' + String(err));
    } finally {
      setImporting(false);
      e.target.value = '';
    }
  };

  return (
    <div className="home">
      <div className="home-header">
        <h1>Requirements</h1>
        <div className="home-actions">
          <label className="btn btn-primary" style={{ cursor: 'pointer' }}>
            {importing ? 'Importing...' : '+ Import Excel'}
            <input type="file" accept=".xlsx,.xls" onChange={handleImport} style={{ display: 'none' }} disabled={importing} />
          </label>
          <button className="btn" onClick={fetchReqs}>Refresh</button>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <div style={{ position: 'relative', flex: 1, maxWidth: 420 }}>
          <input
            ref={searchRef}
            type="text"
            placeholder="Search requirements... (/)"
            value={q}
            onChange={(e) => { setQ(e.target.value); setPage(1); setLoading(true); }}
            style={{
              width: '100%', padding: '8px 12px 8px 32px', border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)', background: 'var(--bg-surface)',
              color: 'var(--text)', fontSize: 13,
            }}
          />
          <span style={{ position: 'absolute', left: 10, top: 8, color: 'var(--text-muted)', fontSize: 13, pointerEvents: 'none' }}>⌕</span>
        </div>
        <div style={{ display: 'flex', gap: 4 }}>
          {['', 'new', 'pending', 'reviewed'].map((s) => (
            <button
              key={s || 'all'}
              className={`filter-chip ${status === s ? 'active' : ''}`}
              onClick={() => { setStatus(s); setPage(1); setLoading(true); }}
            >
              {s ? s.charAt(0).toUpperCase() + s.slice(1) : 'All'}
            </button>
          ))}
        </div>
        <span className="text-muted" style={{ marginLeft: 'auto' }}>
          {loading ? '...' : `${reqs.length} of ${total}`}
        </span>
      </div>

      {error && <div className="error-msg">{error}</div>}

      <table className="req-table">
        <thead>
          <tr><th>Key</th><th>Description</th><th>Function</th><th style={{ textAlign: 'right' }}>Status</th></tr>
        </thead>
        <tbody>
          {reqs.map((r) => (
            <tr key={r.id} onClick={() => navigate(`/requirements/${r.id}`)}>
              <td><span className="req-key">{r.requirement_key}</span></td>
              <td><span className="req-desc">{r.description}</span></td>
              <td style={{ color: 'var(--text-muted)' }}>{r.function_name || '—'}</td>
              <td style={{ textAlign: 'right' }}>{statusBadge(r.status)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {totalPages > 1 && (
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 8, marginTop: 16 }}>
          <button className="btn" disabled={page <= 1} onClick={() => setPage(p => Math.max(1, p - 1))}>
            ← Prev
          </button>
          <span className="text-muted" style={{ fontSize: 13 }}>
            Page {page} of {totalPages}
          </span>
          <button className="btn" disabled={page >= totalPages} onClick={() => setPage(p => Math.min(totalPages, p + 1))}>
            Next →
          </button>
        </div>
      )}

      {!loading && reqs.length === 0 && !error && (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
          No requirements found. Import an Excel file to get started.
        </div>
      )}
    </div>
  );
}
