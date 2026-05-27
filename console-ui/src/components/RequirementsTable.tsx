import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { startRun } from '../api/endpoints'
import { useJob } from '../hooks/JobContext'
import type { Requirement } from '../api/types'

interface Props {
  requirements: Requirement[]
  runMap: Map<string, { status: string; time: string; dir: string }>
  batchId: string
}

const STATUS_LABELS: Record<string, string> = {
  evaluated: 'Evaluated',
  cases_ready: 'Cases Ready',
  intent_ready: 'Intent Ready',
  clarification_ready: 'Clarification Ready',
  clarification_blocked: 'Blocked',
  new: 'New',
}

export default function RequirementsTable({ requirements, runMap, batchId }: Props) {
  const navigate = useNavigate()
  const { isLocked, startPolling } = useJob()
  const [starting, setStarting] = useState<string | null>(null)

  const handleStartRun = async (reqKey: string) => {
    setStarting(reqKey)
    try {
      const res = await startRun({ requirement_key: reqKey, batch_id: batchId })
      if (res.status === 'started') {
        startPolling()
      }
    } catch {
      // error shown by job banner
    } finally {
      setStarting(null)
    }
  }

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
              <td className="actions-cell">
                {r.dir && (
                  <button
                    className="btn btn-sm btn-primary"
                    onClick={() => navigate(`/run/${r.dir}`)}
                  >
                    Open
                  </button>
                )}
                <button
                  className="btn btn-sm"
                  onClick={() => handleStartRun(r.requirement_key)}
                  disabled={isLocked || starting === r.requirement_key}
                >
                  {starting === r.requirement_key ? 'Starting...' : 'Start New Run'}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
