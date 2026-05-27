import { useState, useEffect } from 'react'
import { regenerateConfirm, regenerateExecute } from '../api/endpoints'

interface Props {
  open: boolean
  runDir: string
  stage: string
  onClose: () => void
  onStarted: () => void
}

export default function RegenerateDialog({ open, runDir, stage, onClose, onStarted }: Props) {
  const [confirming, setConfirming] = useState(false)
  const [info, setInfo] = useState<{
    confirmation_required: boolean
    affected_artifacts?: string[]
    message?: string
  } | null>(null)

  useEffect(() => {
    if (open) {
      setInfo(null)
      setConfirming(false)
      regenerateConfirm(runDir, stage)
        .then(setInfo)
        .catch(() => onClose())
    }
  }, [open, runDir, stage, onClose])

  const handleConfirm = async () => {
    setConfirming(true)
    try {
      const res = await regenerateExecute(runDir, stage)
      if (res.status === 'started') {
        onStarted()
        onClose()
      }
    } catch {
      setConfirming(false)
    }
  }

  if (!open) return null

  return (
    <div className="dialog-overlay" onClick={onClose}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <h3>Regenerate {stage}</h3>
        {!info ? (
          <p>Loading confirmation...</p>
        ) : (
          <>
            <p>{info.message || 'This will archive downstream artifacts and regenerate.'}</p>
            {info.affected_artifacts && info.affected_artifacts.length > 0 && (
              <ul className="dialog-details">
                {info.affected_artifacts.map((a) => <li key={a}>{a}</li>)}
              </ul>
            )}
            <div className="dialog-actions">
              <button
                className="btn btn-danger"
                onClick={handleConfirm}
                disabled={confirming}
              >
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
