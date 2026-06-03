import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getRequirement } from '../api/requirements';
import { createRun } from '../api/runs';
import type { Requirement } from '../api/types';

export default function RequirementDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [req, setReq] = useState<Requirement | null>(null);
  const [runs, setRuns] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showConfig, setShowConfig] = useState(false);
  const [reviewA, setReviewA] = useState(false);
  const [reviewB, setReviewB] = useState(false);
  const [reviewC, setReviewC] = useState(false);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    if (!id) return;
    getRequirement(Number(id))
      .then((d) => { setReq(d.requirement); setRuns(d.runs); })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [id]);

  const handleCreateRun = async () => {
    if (!req) return;
    setCreating(true);
    try {
      const rev: string[] = [];
      if (reviewA) rev.push('a');
      if (reviewB) rev.push('b');
      if (reviewC) rev.push('c');
      const run = await createRun(req.id, rev);
      navigate(`/runs/${run.run.id}`);
    } catch (e) {
      setError(String(e));
    } finally {
      setCreating(false);
    }
  };

  if (loading) return <div className="loading"><span className="spinner" /> Loading...</div>;
  if (error) return <div className="error-msg">{error}</div>;
  if (!req) return <div className="error-msg">Requirement not found</div>;

  const statusBadge = (s: string) => {
    if (s === 'evaluated') return <span className="badge badge-done">Evaluated</span>;
    if (s === 'cases_ready') return <span className="badge badge-done">Cases Ready</span>;
    if (s === 'intents_ready') return <span className="badge badge-pending">Intents Ready</span>;
    if (s === 'extraction_ready') return <span className="badge badge-pending">Extraction Ready</span>;
    return <span className="badge badge-new">{s}</span>;
  };

  return (
    <div className="req-detail">
      <button className="btn btn-sm" onClick={() => navigate('/')} style={{ alignSelf: 'flex-start', marginBottom: 16 }}>
        &larr; Back to Requirements
      </button>
      <h1>{req.requirement_key}</h1>
      <div className="req-info">
        <p style={{ color: 'var(--text-muted)', marginBottom: 4 }}>{req.function_name}</p>
        <p>{req.description}</p>
      </div>

      <div style={{ marginBottom: 24 }}>
        <button className="btn btn-primary" onClick={() => setShowConfig(!showConfig)}>
          Start New Run
        </button>
        {showConfig && (
          <div style={{ marginTop: 12, padding: 16, border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', background: 'var(--bg-surface)' }}>
            <h3 style={{ fontSize: 14, marginBottom: 12 }}>Review Configuration</h3>
            <div className="review-config">
              <label><input type="checkbox" checked={reviewA} onChange={(e) => setReviewA(e.target.checked)} /> LLM-A requires review (extraction)</label>
              <label><input type="checkbox" checked={reviewB} onChange={(e) => setReviewB(e.target.checked)} /> LLM-B requires review (case intents)</label>
              <label><input type="checkbox" checked={reviewC} onChange={(e) => setReviewC(e.target.checked)} /> LLM-C requires review (test cases)</label>
            </div>
            <button className="btn btn-primary" onClick={handleCreateRun} disabled={creating} style={{ marginTop: 12 }}>
              {creating ? 'Creating...' : 'Create Run'}
            </button>
          </div>
        )}
      </div>

      {runs.length > 0 && (
        <div>
          <h3 style={{ fontSize: 14, marginBottom: 12 }}>Previous Runs</h3>
          <div className="run-list">
            {runs.map((r) => (
              <div key={r.id} className="run-item" onClick={() => navigate(`/runs/${r.id}`)}>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)' }}>#{r.id}</span>
                {statusBadge(r.status)}
                <span className="text-muted">{new Date(r.created_at + 'Z').toLocaleString()}</span>
                <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-muted)' }}>
                  {r.review_llm_a ? 'A' : ''}{r.review_llm_b ? 'B' : ''}{r.review_llm_c ? 'C' : ''}
                  {!r.review_llm_a && !r.review_llm_b && !r.review_llm_c ? 'Auto' : ' Review'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
