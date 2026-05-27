import { useState } from 'react'
import ValidationSummary from '../components/ValidationSummary'
import ConfirmDialog from '../components/ConfirmDialog'
import { useIntentReview } from '../hooks/useIntentReview'
import { useJob } from '../hooks/JobContext'
import type { IntentReviewItem } from '../api/types'

interface Props { runDir: string }

const DECISIONS = ['approve', 'reject', 'revise', 'merge', 'split', 'defer']
const DECISION_LABELS: Record<string, string> = {
  '': 'All', pending: 'Pending', approve: 'Approve', reject: 'Reject',
  revise: 'Revise', merge: 'Merge', split: 'Split', defer: 'Defer',
}

function IntentDetail({ item, validationErrors, onChange }: {
  item: IntentReviewItem | null
  reasonCodes?: unknown
  validationErrors: string[]
  onChange: (c: Partial<IntentReviewItem>) => void
}) {
  if (!item) return <div className="card review-detail"><p className="text-muted">Select an item.</p></div>

  const showRevise = item.decision === 'revise'
  const showMerge = item.decision === 'merge'
  const showSplit = item.decision === 'split'

  return (
    <div className="card review-detail">
      <h3>{item.intent_id}</h3>
      {validationErrors.length > 0 && (
        <div className="field-errors">
          {validationErrors.map((e, i) => <div key={i} className="field-error">{e}</div>)}
        </div>
      )}
      <div className="detail-grid">
        {item.coverage_dimension && (
          <div className="detail-field"><label>Coverage Dimension</label><span>{item.coverage_dimension}</span></div>
        )}
        {item.intent_text && (
          <div className="detail-field"><label>Intent Text</label><div className="affected-text">{item.intent_text}</div></div>
        )}
        {item.routing_color && (
          <div className="detail-field"><label>Confidence</label><span className={`routing-dot routing-${item.routing_color}`}></span> {item.routing_color}</div>
        )}
        {item.recommended_decision && (
          <div className="detail-field"><label>Recommended</label><span>{item.recommended_decision}</span></div>
        )}
      </div>

      <div className="detail-decisions">
        <div className="form-group">
          <label>Decision</label>
          <select value={item.decision || ''} onChange={(e) => onChange({ decision: e.target.value })}>
            <option value="">-- Choose --</option>
            {DECISIONS.map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>

        <div className="form-group">
          <label>Reason Text</label>
          <textarea value={item.reason_text || ''} onChange={(e) => onChange({ reason_text: e.target.value })} rows={3} />
        </div>

        {showRevise && (
          <div className="form-group">
            <label>Revised Intent Text</label>
            <textarea value={item.revised_intent_text || ''} onChange={(e) => onChange({ revised_intent_text: e.target.value })} rows={3} />
          </div>
        )}

        {showMerge && (
          <div className="form-group">
            <label>Merge Target Intent ID</label>
            <input value={item.merge_target_id || ''} onChange={(e) => onChange({ merge_target_id: e.target.value })} />
          </div>
        )}

        {showSplit && (
          <div className="form-group">
            <label>Split Children (JSON array)</label>
            <textarea
              value={JSON.stringify(item.split_children || [], null, 2)}
              onChange={(e) => {
                try { onChange({ split_children: JSON.parse(e.target.value) }) } catch { /* invalid JSON */ }
              }}
              rows={4}
            />
          </div>
        )}
      </div>
    </div>
  )
}

export default function IntentReviewPage({ runDir }: Props) {
  const {
    items, selectedId, selectedItem, loading, error,
    validationErrors,
    setSelectedId, updateDraftItem, saveDraft, generate,
    refetch, isDirty, setValidationErrors,
  } = useIntentReview(runDir)
  const { isLocked, startPolling } = useJob()
  const [statusMsg, setStatusMsg] = useState<string | null>(null)
  const [regenerateConfirm, setRegenerateConfirm] = useState(false)

  const handleSaveDraft = async () => {
    const r = await saveDraft()
    setStatusMsg(r?.success ? 'Draft saved.' : (r as { error?: string })?.error || 'Save failed')
    if (r?.success) { refetch(); setValidationErrors(new Map()) }
  }

  const handleGenerate = async () => {
    const raw = await generate()
    if (!raw) return
    const res = raw as Record<string, unknown>
    if (res.status === 'started') {
      startPolling()
      setStatusMsg('Generation started...')
    } else if (res.validated === false && res.errors) {
      const errMap = new Map<string, string[]>()
      for (const e of (res.errors as Array<Record<string, unknown>>)) {
        const id = String(e.intent_id || e.item_id || 'unknown')
        const msgs = errMap.get(id) || []
        msgs.push(String(e.message || ''))
        errMap.set(id, msgs)
      }
      setValidationErrors(errMap)
      setStatusMsg('Validation failed.')
    } else {
      setStatusMsg('Cases generated!')
      refetch()
    }
  }

  const handleRegenerateConfirm = () => setRegenerateConfirm(true)

  if (loading) return <div className="card"><p>Loading intent review...</p></div>
  if (error) return <div className="error-msg">{error}</div>

  const itemErrors = selectedId ? validationErrors.get(selectedId) || [] : []

  return (
    <div className="intent-review">
      {statusMsg && (
        <div className="card status-msg">
          {statusMsg}
          <button className="btn btn-sm" onClick={() => setStatusMsg(null)}>Dismiss</button>
        </div>
      )}
      <ValidationSummary errors={validationErrors} onSelectItem={(id) => setSelectedId(id)} />

      <div className="review-actions">
        <button className="btn btn-primary" onClick={handleSaveDraft} disabled={isLocked || !isDirty}>
          Save Draft
        </button>
        <button className="btn btn-primary" onClick={handleGenerate} disabled={isLocked || !isDirty}>
          Save &amp; Generate Cases
        </button>
        <button className="btn btn-sm" onClick={handleRegenerateConfirm} disabled={isLocked}>
          Regenerate
        </button>
      </div>

      <div className="review-body">
        <div className="review-queue">
          <div className="queue-list">
            {items.map((item) => {
              const dec = item.decision || 'pending'
              return (
                <button
                  key={item.intent_id}
                  className={`queue-row ${item.intent_id === selectedId ? 'selected' : ''}`}
                  onClick={() => setSelectedId(item.intent_id)}
                >
                  <span className={`routing-dot routing-${item.routing_color || 'blue'}`} />
                  <span className="queue-item-id">{item.intent_id}</span>
                  <span className={`queue-decision dec-${dec}`}>
                    {DECISION_LABELS[dec] || dec}
                  </span>
                  {item.coverage_dimension && (
                    <span className="queue-type text-muted">{item.coverage_dimension}</span>
                  )}
                </button>
              )
            })}
          </div>
        </div>

        <IntentDetail
          item={selectedItem}
          validationErrors={itemErrors}
          onChange={(changes) => selectedId && updateDraftItem(selectedId, changes)}
        />
      </div>

      <RegenerateDialog
        open={regenerateConfirm}
        runDir={runDir}
        stage="intents"
        onClose={() => setRegenerateConfirm(false)}
        onStarted={startPolling}
      />
    </div>
  )
}

function RegenerateDialog({ open, runDir, stage, onClose, onStarted }: {
  open: boolean; runDir: string; stage: string; onClose: () => void; onStarted: () => void
}) {
  const [confirming, setConfirming] = useState(false)
  const [info, setInfo] = useState<{ confirmation_required: boolean; affected_artifacts?: string[]; message?: string } | null>(null)

  const handleOpen = async () => {
    try {
      const { regenerateConfirm } = await import('../api/endpoints')
      const result = await regenerateConfirm(runDir, stage)
      setInfo(result)
    } catch { onClose() }
  }

  const handleConfirm = async () => {
    setConfirming(true)
    try {
      const { regenerateExecute } = await import('../api/endpoints')
      const res = await regenerateExecute(runDir, stage)
      if (res.status === 'started') { onStarted(); onClose() }
    } catch { setConfirming(false) }
  }

  if (!open) return null

  return (
    <div className="dialog-overlay" onClick={onClose}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <h3>Regenerate {stage}</h3>
        {!info ? (
          <>
            <p>Loading confirmation...</p>
            {setTimeout(handleOpen, 0) as unknown as null}
          </>
        ) : (
          <>
            <p>{info.message || `This will regenerate downstream artifacts.`}</p>
            {info.affected_artifacts && info.affected_artifacts.length > 0 && (
              <ul className="dialog-details">
                {info.affected_artifacts.map((a) => <li key={a}>{a}</li>)}
              </ul>
            )}
            <div className="dialog-actions">
              <button className="btn btn-danger" onClick={handleConfirm} disabled={confirming}>
                {confirming ? 'Regenerating...' : 'Confirm Regenerate'}
              </button>
              <button className="btn" onClick={onClose}>Cancel</button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
