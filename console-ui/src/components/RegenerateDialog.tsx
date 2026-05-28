import { useState } from 'react'
import { regenerateCase } from '../api/endpoints'

interface Props {
  open: boolean
  runDir: string
  caseId: string
  intentId: string
  onClose: () => void
  onStarted: () => void
}

export default function RegenerateDialog({ open, runDir, caseId, intentId, onClose, onStarted }: Props) {
  const [reviewComment, setReviewComment] = useState('')
  const [submitting, setSubmitting] = useState(false)

  if (!open) return null

  const handleSubmit = async () => {
    setSubmitting(true)
    try {
      const res = await regenerateCase(runDir, [{ case_id: caseId, intent_id: intentId, review_comment: reviewComment }])
      if (res.status === 'started') {
        onStarted()
        onClose()
      }
    } catch {
      setSubmitting(false)
    }
  }

  return (
    <div className="dialog-overlay" onClick={onClose}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <h3>Regenerate Case: {caseId}</h3>
        <p>Provide a review comment describing what should change in the regenerated case.</p>
        <div className="form-group">
          <label>Review Comment</label>
          <textarea
            value={reviewComment}
            onChange={(e) => setReviewComment(e.target.value)}
            rows={4}
            placeholder="e.g., Add missing edge case for timeout scenario..."
          />
        </div>
        <div className="dialog-actions">
          <button
            className="btn btn-primary"
            onClick={handleSubmit}
            disabled={submitting || !reviewComment.trim()}
          >
            {submitting ? 'Regenerating...' : 'Regenerate'}
          </button>
          <button className="btn" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  )
}
