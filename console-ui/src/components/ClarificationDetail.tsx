import type { ReviewItem, ReasonCodes, MemoryHints } from '../api/types'

interface Props {
  item: ReviewItem | null
  reasonCodes: ReasonCodes | null
  memoryHints: MemoryHints | null
  validationErrors: string[]
  onChange: (changes: Partial<ReviewItem>) => void
}

export default function ClarificationDetail({ item, reasonCodes, memoryHints, validationErrors, onChange }: Props) {
  if (!item) {
    return <div className="card review-detail"><p className="text-muted">Select an item from the queue.</p></div>
  }

  const decisions = reasonCodes?.decisions || ['approve', 'clarify', 'mark_needs_review', 'block', 'edit_content']
  const codes = reasonCodes?.reason_codes || {}
  const reqs = reasonCodes?.decision_requirements || {}

  return (
    <div className="card review-detail">
      <h3>{item.item_id}</h3>

      {validationErrors.length > 0 && (
        <div className="field-errors">
          {validationErrors.map((e, i) => <div key={i} className="field-error">{e}</div>)}
        </div>
      )}

      <div className="detail-grid">
        {item.affected_text && (
          <div className="detail-field">
            <label>Affected Text</label>
            <div className="detail-value affected-text">{item.affected_text}</div>
          </div>
        )}

        {item.ambiguity_type && (
          <div className="detail-field">
            <label>Ambiguity Type</label>
            <span>{item.ambiguity_type}</span>
          </div>
        )}

        {item.impact && (
          <div className="detail-field">
            <label>Impact</label>
            <span>{item.impact}</span>
          </div>
        )}

        {item.severity && (
          <div className="detail-field">
            <label>Severity</label>
            <span>{item.severity}</span>
          </div>
        )}

        {item.clarification_question && (
          <div className="detail-field">
            <label>Clarification Question</label>
            <div className="detail-value">{item.clarification_question}</div>
          </div>
        )}

        {item.confidence_drivers && Object.keys(item.confidence_drivers).length > 0 && (
          <div className="detail-field">
            <label>Confidence Drivers</label>
            <div className="confidence-drivers">
              {Object.entries(item.confidence_drivers).map(([k, v]) => (
                <span key={k} className="confidence-item">
                  {k}: {typeof v === 'number' ? v.toFixed(2) : String(v)}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="detail-decisions">
        <div className="form-group">
          <label>Decision</label>
          <select
            value={item.decision || ''}
            onChange={(e) => onChange({ decision: e.target.value })}
          >
            <option value="">-- Choose --</option>
            {decisions.map((d) => (
              <option key={d} value={d}>{d.replace(/_/g, ' ')}</option>
            ))}
          </select>
        </div>

        <div className="form-group">
          <label>Reason Codes</label>
          <div className="reason-code-list">
            {(codes[item.decision] || []).map((rc: string) => (
              <label key={rc} className="reason-code-item">
                <input
                  type="checkbox"
                  checked={(item.reason_codes || []).includes(rc)}
                  onChange={(e) => {
                    const next = e.target.checked
                      ? [...(item.reason_codes || []), rc]
                      : (item.reason_codes || []).filter((c: string) => c !== rc)
                    onChange({ reason_codes: next })
                  }}
                />
                {rc}
              </label>
            ))}
          </div>
        </div>

        <div className="form-group">
          <label>Reason Text</label>
          <textarea
            value={item.reason_text || ''}
            onChange={(e) => onChange({ reason_text: e.target.value })}
            rows={3}
          />
        </div>

        <div className="form-group">
          <label>Clarified Value</label>
          <textarea
            value={item.clarified_value || ''}
            onChange={(e) => onChange({ clarified_value: e.target.value })}
            rows={2}
          />
        </div>
      </div>

      {memoryHints && memoryHints.hints.length > 0 && (
        <div className="memory-hints">
          <h4>Review Memory Hints (advisory)</h4>
          <ul>
            {memoryHints.hints.map((h, i) => <li key={i}>{h}</li>)}
          </ul>
          <p className="text-muted hint-note">{memoryHints.advisory_note}</p>
        </div>
      )}
    </div>
  )
}
