import type { TestCase, CaseIntent } from '../api/types';

interface Props {
  case_: TestCase;
  intent: CaseIntent | null;
  index: number;
  dimLabel: string;
  onEditCase?: (case_: TestCase) => void;
}

function renderWithNeedsReview(text: string) {
  const parts = text.split(/(\[NEEDS REVIEW\])/gi);
  return parts.map((p, i) =>
    p.toUpperCase() === '[NEEDS REVIEW]' ? (
      <span key={i} className="needs-review">[NEEDS REVIEW]</span>
    ) : (
      <span key={i}>{p}</span>
    )
  );
}

export default function CaseGroup({ case_, intent, index, dimLabel, onEditCase }: Props) {
  const evalItems = case_.evaluation_items || [];
  const failed = evalItems.filter((e) => e.result === 'fail');
  const warned = evalItems.filter((e) => e.result === 'warn');
  const hasEval = evalItems.length > 0;
  const evFailed = hasEval && failed.length > 0;
  const evPassed = hasEval && failed.length === 0;

  return (
    <div className="case-group">
      {intent && (
        <div className="case-intent-bar">
          <span className="case-intent-num">#{index + 1}</span>
          <span className="case-intent-dimension">{dimLabel}</span>
          <span className="case-intent-text">{intent.intent_text}</span>
        </div>
      )}

      <div className="case-body">
        <div className="case-header-bar">
          <span className="case-title">
            <span className="case-tag">Case {index + 1}</span>
            {case_.title}
          </span>
          <div style={{ display: 'flex', gap: 6 }}>
            {evPassed && <span className="badge badge-done">✓ Passed</span>}
            {evFailed && <span className="badge" style={{ background: 'var(--danger-subtle)', color: 'var(--danger)' }}>✗ Failed</span>}
            <button className="btn btn-xs" onClick={() => onEditCase?.(case_)}>Edit</button>
            <button className="btn btn-xs">Regenerate</button>
            <button className="btn btn-xs btn-primary">Accept</button>
          </div>
        </div>

        <div className="case-meta">
          <div>
            <div className="case-meta-label">Objective</div>
            <div className="case-meta-value">{case_.objective}</div>
          </div>
        </div>

        <div className="case-meta">
          <div>
            <div className="case-meta-label">Precondition</div>
            <div className="case-meta-value">{case_.precondition}</div>
          </div>
          <div>
            <div className="case-meta-label">Postcondition</div>
            <div className="case-meta-value">{case_.postcondition}</div>
          </div>
        </div>

        <table className="steps-table">
          <thead>
            <tr><th style={{ width: 1 }} />{/* */}<th style={{ width: '48%' }}>Action</th><th>Expected</th></tr>
          </thead>
          <tbody>
            {case_.steps.map((s) => (
              <tr key={s.step_order}>
                <td style={{ textAlign: 'center' }}><span className="step-num">{s.step_order}</span></td>
                <td>{renderWithNeedsReview(s.action)}</td>
                <td style={{ color: 'var(--text-secondary)' }}>{renderWithNeedsReview(s.expected)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        {hasEval && (failed.length > 0 || warned.length > 0) && (
          <div style={{ padding: '12px 20px', borderTop: '1px solid var(--border)', fontSize: 12 }}>
            {failed.length > 0 && (
              <span style={{ color: 'var(--danger)' }}>
                Failed: {failed.map((e) => e.item_id).join(', ')}
              </span>
            )}
            {warned.length > 0 && (
              <span style={{ color: 'var(--warning)', marginLeft: 12 }}>
                Warning: {warned.map((e) => e.item_id).join(', ')}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
