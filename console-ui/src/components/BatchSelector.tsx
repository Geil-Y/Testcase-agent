import { useState } from 'react'
import type { ImportBatchSummary } from '../api/types'

interface Props {
  batches: ImportBatchSummary[]
  selectedId: string | null
  onSelect: (batchId: string) => void
}

export default function BatchSelector({ batches, selectedId, onSelect }: Props) {
  const [search, setSearch] = useState('')

  const filtered = search.trim()
    ? batches.filter((b) =>
        b.filename.toLowerCase().includes(search.toLowerCase()) ||
        b.id.toLowerCase().includes(search.toLowerCase())
      )
    : batches

  if (batches.length === 0) {
    return <p className="text-muted">No import batches yet.</p>
  }

  return (
    <div className="card batch-selector">
      <h3>Import Batches</h3>
      {batches.length > 6 && (
        <input
          type="text"
          className="queue-search"
          placeholder="Filter batches..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ marginBottom: 8, width: '100%' }}
        />
      )}
      <div className="batch-list">
        {filtered.map((b) => (
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
        {filtered.length === 0 && (
          <p className="text-muted" style={{ padding: '4px 0' }}>No matching batches.</p>
        )}
      </div>
    </div>
  )
}
