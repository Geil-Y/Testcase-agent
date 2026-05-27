import type { ImportBatchSummary } from '../api/types'

interface Props {
  batches: ImportBatchSummary[]
  selectedId: string | null
  onSelect: (batchId: string) => void
}

export default function BatchSelector({ batches, selectedId, onSelect }: Props) {
  if (batches.length === 0) {
    return <p className="text-muted">No import batches yet.</p>
  }

  return (
    <div className="card batch-selector">
      <h3>Import Batches</h3>
      <div className="batch-list">
        {batches.map((b) => (
          <button
            key={b.id}
            className={`btn btn-sm ${b.id === selectedId ? 'btn-primary' : ''}`}
            onClick={() => onSelect(b.id)}
          >
            <span className="batch-name">{b.filename}</span>
            <span className="batch-meta">
              {b.requirements_count} reqs &middot; {new Date(b.created_at).toLocaleDateString()}
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}
