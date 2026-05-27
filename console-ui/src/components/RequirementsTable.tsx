import { useNavigate } from 'react-router-dom'
import type { Requirement } from '../api/types'

interface Props {
  requirements: Requirement[]
  runMap: Map<string, { status: string; time: string; dir: string }>
}

const STATUS_LABELS: Record<string, string> = {
  evaluated: 'Evaluated',
  cases_ready: 'Cases Ready',
  intent_ready: 'Intent Ready',
  clarification_ready: 'Clarification Ready',
  clarification_blocked: 'Blocked',
  new: 'New',
}

export default function RequirementsTable({ requirements, runMap }: Props) {
  const navigate = useNavigate()

  const rows = requirements
    .filter((r) => !r.is_heading && !r.is_info)
    .map((r) => {
      const run = runMap.get(r.requirement_key)
      return { ...r, ...run }
    })

  return (
    <div className="card">
      <h3>Requirements ({rows.length})</h3>
      <table className="table">
        <thead>
          <tr>
            <th>Key</th>
            <th>Description</th>
            <th>Type</th>
            <th>Latest Run</th>
            <th>Last Run Time</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.requirement_key}>
              <td><code>{r.requirement_key}</code></td>
              <td>{r.description?.slice(0, 80)}{(r.description?.length || 0) > 80 ? '...' : ''}</td>
              <td>{r.function_name || r.requirement_type || '-'}</td>
              <td>
                {r.status ? (
                  <span className={`badge badge-status-${r.status}`}>
                    {STATUS_LABELS[r.status] || r.status}
                  </span>
                ) : (
                  <span className="text-muted">No runs</span>
                )}
              </td>
              <td className="text-muted">{r.time ? new Date(r.time).toLocaleString() : '-'}</td>
              <td>
                {r.dir && (
                  <button
                    className="btn btn-sm btn-primary"
                    onClick={() => navigate(`/run/${r.dir}`)}
                  >
                    Open Latest Run
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
