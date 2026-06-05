import { useState } from 'react';
import type { TestCase, CaseStepPayload } from '../api/types';
import { updateCase } from '../api/runs';

interface Props {
  case_: TestCase;
  runId: number;
  onClose: () => void;
  onSaved: () => void;
}

export default function CaseEditModal({ case_, runId, onClose, onSaved }: Props) {
  const [title, setTitle] = useState(case_.title);
  const [objective, setObjective] = useState(case_.objective);
  const [precondition, setPrecondition] = useState(case_.precondition);
  const [postcondition, setPostcondition] = useState(case_.postcondition);
  const [steps, setSteps] = useState<CaseStepPayload[]>(
    case_.steps.map((s) => ({ step_order: s.step_order, action: s.action, expected: s.expected }))
  );
  const [saving, setSaving] = useState(false);

  const handleAddStep = () => {
    setSteps((prev) => [...prev, { step_order: prev.length + 1, action: '', expected: '' }]);
  };

  const handleRemoveStep = (idx: number) => {
    setSteps((prev) =>
      prev.filter((_, i) => i !== idx).map((s, i) => ({ ...s, step_order: i + 1 }))
    );
  };

  const handleStepChange = (idx: number, field: 'action' | 'expected', value: string) => {
    setSteps((prev) => prev.map((s, i) => (i === idx ? { ...s, [field]: value } : s)));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateCase(runId, case_.id, {
        title,
        objective,
        precondition,
        postcondition,
        steps: steps.filter((s) => s.action || s.expected),
      });
      onSaved();
      onClose();
    } catch (e) {
      alert('Save failed: ' + String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" style={{ maxWidth: 960, width: '90vw' }} onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Edit Case</h3>
          <button className="modal-close" onClick={onClose}>&times;</button>
        </div>
        <div className="modal-body" style={{ maxHeight: '70vh', overflow: 'auto' }}>
          <div className="mf">
            <label>Title</label>
            <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="mf">
            <label>Objective</label>
            <textarea value={objective} onChange={(e) => setObjective(e.target.value)} rows={2} />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div className="mf">
              <label>Precondition</label>
              <textarea value={precondition} onChange={(e) => setPrecondition(e.target.value)} rows={2} />
            </div>
            <div className="mf">
              <label>Postcondition</label>
              <textarea value={postcondition} onChange={(e) => setPostcondition(e.target.value)} rows={2} />
            </div>
          </div>

          <div style={{ marginTop: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <label style={{ fontWeight: 600, fontSize: 13 }}>Steps</label>
              <button className="btn btn-xs" onClick={handleAddStep}>+ Add Step</button>
            </div>
            {steps.length === 0 && (
              <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: '8px 0' }}>No steps defined.</div>
            )}
            {steps.map((step, idx) => (
              <div key={idx} style={{ display: 'grid', gridTemplateColumns: '28px 1fr 1fr 28px', gap: 10, marginBottom: 12, alignItems: 'start' }}>
                <span style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: 13, paddingTop: 8 }}>{step.step_order}</span>
                <textarea
                  placeholder="Action..."
                  value={step.action}
                  onChange={(e) => handleStepChange(idx, 'action', e.target.value)}
                  rows={3}
                />
                <textarea
                  placeholder="Expected..."
                  value={step.expected}
                  onChange={(e) => handleStepChange(idx, 'expected', e.target.value)}
                  rows={3}
                />
                <button className="btn btn-xs" style={{ padding: '2px 6px', fontSize: 12 }} onClick={() => handleRemoveStep(idx)} title="Remove step">&times;</button>
              </div>
            ))}
          </div>
        </div>
        <div className="modal-footer">
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
