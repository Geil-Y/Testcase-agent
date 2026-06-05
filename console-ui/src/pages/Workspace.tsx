import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getRun, advanceRun, evaluateRun, addItem, deleteItem, deleteIntent, regenerateIntents, getReviewState, acceptStage, unlockStage } from '../api/runs';
import type { RunDetail, ReviewState, SectionItem, TestCase } from '../api/types';
import Sidebar from '../components/Sidebar';
import CaseGroup from '../components/CaseGroup';
import IntentsPanel from '../components/IntentsPanel';
import ItemModal from '../components/ItemModal';
import CaseEditModal from '../components/CaseEditModal';
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
  const [reviewState, setReviewState] = useState<ReviewState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [advancing, setAdvancing] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [toast, setToast] = useState('');
  const [modalItem, setModalItem] = useState<{ item: SectionItem; sectionName: string; isNew: boolean } | null>(null);
  const [editingCase, setEditingCase] = useState<TestCase | null>(null);

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

  const fetchReviewState = useCallback(async () => {
    if (!runId) return;
    try {
      const rs = await getReviewState(Number(runId));
      setReviewState(rs);
    } catch { /* endpoint may not exist yet */ }
  }, [runId]);

  useEffect(() => { fetchRun(); fetchReviewState(); }, [runId, fetchReviewState]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (editingCase) { setEditingCase(null); }
        else if (modalItem) { setModalItem(null); }
        else { navigate('/'); }
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [modalItem, editingCase]);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(''), 4000);
  };

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

  const handleDeleteIntent = async (intent: { id: number }) => {
    if (!runId || !window.confirm('Delete this intent?')) return;
    try {
      await deleteIntent(Number(runId), intent.id);
      await fetchRun();
    } catch (e) {
      setError(String(e));
    }
  };

  const handleRegenerateIntents = async () => {
    if (!runId) return;
    setRegenerating(true);
    try {
      await regenerateIntents(Number(runId));
      await fetchRun();
    } catch (e) {
      setError(String(e));
    } finally {
      setRegenerating(false);
    }
  };

  const handleAdvance = async () => {
    if (!runId) return;
    setAdvancing(true);
    try {
      await advanceRun(Number(runId));
      await fetchRun();
      await fetchReviewState();
    } catch (e: any) {
      if (String(e).includes('409') || String(e).includes('not yet accepted')) {
        showToast('请先 Accept 当前阶段');
      } else {
        setError(String(e));
      }
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

  const handleAccept = async (stage: string) => {
    if (!runId) return;
    try {
      await acceptStage(Number(runId), stage);
      await fetchRun();
      await fetchReviewState();
    } catch (e) {
      setError(String(e));
    }
  };

  const handleUnlock = async (stage: string) => {
    if (!runId) return;
    try {
      await unlockStage(Number(runId), stage, false);
      await fetchRun();
      await fetchReviewState();
    } catch (e) {
      setError(String(e));
    }
  };

  if (loading) return <div className="loading"><span style={{ marginRight: 8 }}>⟳</span>Loading run...</div>;
  if (error) return <div className="error-msg">{error}</div>;
  if (!data) return <div className="error-msg">Run not found</div>;

  const { run, requirement, sections, intents, cases, evaluation } = data;
  const status = run.status;
  const llmA = reviewState?.a;
  const llmAAccepted = llmA?.accepted ?? false;
  const llmARequired = llmA?.review_required ?? false;

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
        {status === 'extraction_ready' && llmARequired && (
          llmAAccepted ? (
            <button className="btn btn-sm" onClick={() => handleUnlock('a')} style={{ marginLeft: 8 }}>Unlock LLM-A</button>
          ) : (
            <button className="btn btn-sm btn-accept" onClick={() => handleAccept('a')} style={{ marginLeft: 8 }}>Accept LLM-A</button>
          )
        )}
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
          accepted={llmAAccepted}
          runId={Number(runId)}
          onRegenerated={fetchRun}
        />
        <div className="main-content">
          {status === 'intents_ready' && (
            <IntentsPanel
              intents={intents}
              onDelete={handleDeleteIntent}
              onRegenerate={handleRegenerateIntents}
              regenerating={regenerating}
            />
          )}

          {(status === 'cases_ready' || status === 'evaluated') && (
            <>
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
                      onEditCase={setEditingCase}
                    />
                  );
                })
              )}
            </>
          )}

          {status === 'extraction_ready' && cases.length === 0 && (
            <div className="empty-state">
              <h3>Intents not yet planned</h3>
              <p>Complete extraction review and advance to plan case intents.</p>
            </div>
          )}
        </div>
      </div>

      {toast && <div className="toast">{toast}</div>}

      {modalItem && (
        <ItemModal
          item={modalItem.item}
          sectionName={modalItem.sectionName}
          requirementDescription={requirement.description}
          runId={Number(runId)}
          onClose={() => setModalItem(null)}
          onSaved={fetchRun}
          isNew={modalItem.isNew}
          accepted={llmAAccepted}
        />
      )}

      {editingCase && (
        <CaseEditModal
          case_={editingCase}
          runId={Number(runId)}
          onClose={() => setEditingCase(null)}
          onSaved={fetchRun}
        />
      )}
    </div>
  );
}
