import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getRun, advanceRun, evaluateRun, addItem, deleteItem } from '../api/runs';
import type { RunDetail, SectionItem } from '../api/types';
import Sidebar from '../components/Sidebar';
import CaseGroup from '../components/CaseGroup';
import ItemModal from '../components/ItemModal';
import EvaluationSummary from '../components/EvaluationSummary';

const DIM_LABELS: Record<string, string> = {
  normal_behavior: 'Normal Behavior',
  boundary_or_threshold: 'Boundary / Threshold',
  fault_or_protection: 'Fault / Protection',
  state_transition: 'State Transition',
  observability: 'Observability',
};

export default function Workspace() {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<RunDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [advancing, setAdvancing] = useState(false);
  const [modalItem, setModalItem] = useState<{ item: SectionItem; sectionName: string; isNew: boolean } | null>(null);

  const fetchRun = async () => {
    if (!runId) return;
    try {
      setError('');
      const d = await getRun(Number(runId));
      setData(d);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchRun(); }, [runId]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (modalItem) { setModalItem(null); }
        else { navigate('/'); }
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [modalItem]);

  const handleAddItem = (sectionName: string) => {
    const empty: SectionItem = { id: 0, item_id: '', status: 'known', content: '', need: '', source_text: '', sort_order: 0 };
    setModalItem({ item: empty, sectionName, isNew: true });
  };

  const handleDeleteItem = async (item: SectionItem, sectionName: string) => {
    if (!runId || !window.confirm(`Delete item "${item.item_id}"?`)) return;
    try {
      await deleteItem(Number(runId), sectionName, item.item_id);
      await fetchRun();
    } catch (e) {
      setError(String(e));
    }
  };

  const handleAdvance = async () => {
    if (!runId) return;
    setAdvancing(true);
    try {
      await advanceRun(Number(runId));
      await fetchRun();
    } catch (e) {
      setError(String(e));
    } finally {
      setAdvancing(false);
    }
  };

  const handleEvaluate = async () => {
    if (!runId) return;
    setAdvancing(true);
    try {
      await evaluateRun(Number(runId));
      await fetchRun();
    } catch (e) {
      setError(String(e));
    } finally {
      setAdvancing(false);
    }
  };

  if (loading) return <div className="loading"><span style={{ marginRight: 8 }}>⟳</span>Loading run...</div>;
  if (error) return <div className="error-msg">{error}</div>;
  if (!data) return <div className="error-msg">Run not found</div>;

  const { run, requirement, sections, intents, cases, evaluation } = data;
  const status = run.status;

  let actionBtn = null;
  if (status === 'extraction_ready') actionBtn = <button className="btn btn-primary" onClick={handleAdvance} disabled={advancing}>{advancing ? 'Planning...' : 'Plan Case Intents'}</button>;
  else if (status === 'intents_ready') actionBtn = <button className="btn btn-primary" onClick={handleAdvance} disabled={advancing}>{advancing ? 'Generating...' : 'Generate Cases'}</button>;
  else if (status === 'cases_ready') actionBtn = <button className="btn btn-primary" onClick={handleEvaluate} disabled={advancing}>{advancing ? 'Evaluating...' : 'Run Evaluation'}</button>;
  else if (status === 'evaluated') actionBtn = <button className="btn btn-sm" onClick={handleEvaluate} disabled={advancing}>Re-evaluate</button>;

  return (
    <div className="workspace">
      <div className="ws-topbar">
        <button className="ws-back" onClick={() => navigate('/')}>&larr; Requirements</button>
        <span className="ws-req-key">{requirement.requirement_key}</span>
        <span className="ws-req-desc">{requirement.description?.slice(0, 80)}…</span>
        <span className={`badge ${status === 'evaluated' ? 'badge-done' : 'badge-pending'}`}>
          {status.replace(/_/g, ' ')}
        </span>
        <span className="ws-spacer" />
        {actionBtn}
      </div>
      <div className="ws-body">
        <Sidebar
          requirement={requirement}
          sections={sections}
          onItemClick={(item, sectionName) => setModalItem({ item, sectionName, isNew: false })}
          onAddItem={handleAddItem}
          onDeleteItem={handleDeleteItem}
        />
        <div className="main-content">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
              <h2 style={{ fontSize: 16, fontWeight: 600 }}>Test Cases</h2>
              {cases.length > 0 && <span className="badge badge-done">{cases.length} cases</span>}
            </div>
          </div>

          {evaluation && <EvaluationSummary evaluation={evaluation} cases={cases} />}

          {cases.length === 0 ? (
            <div className="empty-state">
              <h3>Cases not yet generated</h3>
              <p>Complete extraction review and advance to generate case intents and test cases.</p>
            </div>
          ) : (
            cases.map((c, idx) => {
              const intent = intents.find((i) => i.id === c.intent_id);
              return (
                <CaseGroup
                  key={c.id}
                  case_={c}
                  intent={intent || null}
                  index={idx}
                  dimLabel={intent ? DIM_LABELS[intent.coverage_dimension] || intent.coverage_dimension : ''}
                />
              );
            })
          )}
        </div>
      </div>

      {modalItem && (
        <ItemModal
          item={modalItem.item}
          sectionName={modalItem.sectionName}
          requirementDescription={requirement.description}
          runId={Number(runId)}
          onClose={() => setModalItem(null)}
          onSaved={fetchRun}
          isNew={modalItem.isNew}
        />
      )}
    </div>
  );
}
