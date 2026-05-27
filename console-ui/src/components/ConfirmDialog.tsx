interface Props {
  open: boolean
  title: string
  message: string
  details?: string[]
  confirmLabel?: string
  danger?: boolean
  onConfirm: () => void
  onCancel: () => void
}

export default function ConfirmDialog({ open, title, message, details, confirmLabel = 'Confirm', danger, onConfirm, onCancel }: Props) {
  if (!open) return null

  return (
    <div className="dialog-overlay" onClick={onCancel}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <h3>{title}</h3>
        <p>{message}</p>
        {details && details.length > 0 && (
          <ul className="dialog-details">
            {details.map((d, i) => <li key={i}>{d}</li>)}
          </ul>
        )}
        <div className="dialog-actions">
          <button className={`btn ${danger ? 'btn-danger' : 'btn-primary'}`} onClick={onConfirm}>
            {confirmLabel}
          </button>
          <button className="btn" onClick={onCancel}>Cancel</button>
        </div>
      </div>
    </div>
  )
}
