interface Props {
  errors: Map<string, string[]>
  onSelectItem?: (itemId: string) => void
}

export default function ValidationSummary({ errors, onSelectItem }: Props) {
  if (errors.size === 0) return null

  const entries = Array.from(errors.entries())

  return (
    <div className="validation-summary card">
      <h4>Validation Errors ({entries.length} items)</h4>
      <ul>
        {entries.map(([itemId, msgs]) => (
          <li key={itemId}>
            <button
              className="btn btn-sm"
              onClick={() => onSelectItem?.(itemId)}
            >
              {itemId}
            </button>
            {msgs.map((m, i) => (
              <span key={i} className="validation-msg">{m}</span>
            ))}
          </li>
        ))}
      </ul>
    </div>
  )
}
