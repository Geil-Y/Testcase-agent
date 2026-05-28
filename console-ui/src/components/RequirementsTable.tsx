import { useState, useEffect } from 'react'
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
  new: 'New',
  extraction_pending_review: 'Extraction Pending',
  extraction_reviewed: 'Extraction Reviewed',
  extraction_blocked: 'Extraction Blocked',
  intents_pending_review: 'Intents Pending',
  intents_reviewed: 'Intents Reviewed',
  intents_blocked: 'Intents Blocked',
  cases_pending_review: 'Cases Pending',
  cases_reviewed: 'Cases Reviewed',
  legacy_unsupported: 'Legacy',
}

export default function RequirementsTable({ requirements, runMap, batchId }: Props) {
  const navigate = useNavigate()
  const { isLocked, startPolling, status: jobStatus, result: jobResult, job } = useJob()
  const [starting, setStarting] = useState<string | null>(null)
  const [pendingStart, setPendingStart] = useState<string | null>(null)
  const [startError, setStartError] = useState<string | null>(null)

  // Navigate to workspace when the start-run job completes successfully
  useEffect(() => {
    if (!pendingStart) return
    if (jobStatus === 'succeeded') {
      const runDir =
        job?.run_dir ||
        (jobResult as Record<string, unknown> | undefined)?.['run_dir'] as string | undefined
      if (runDir) {
        navigate(`/run/${runDir}`)
      } else {
        setPendingStart(null)
      }
    }
    if (jobStatus === 'failed' || jobStatus === 'retryable') {
      setPendingStart(null)
    }
  }, [pendingStart, jobStatus, jobResult, job?.run_dir, navigate])

  const handleStartRun = async (reqKey: string) => {
    setStarting(reqKey)
    setStartError(null)
    try {
      const res = await startRun({ requirement_key: reqKey, batch_id: batchId })
      if (res.status === 'started') {
        setPendingStart(reqKey)
        startPolling()
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to start run'
      setStartError(msg)
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
      {startError && <div className="error-msg">{startError}</div>}
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
              <td className="desc-cell">{r.description || '-'}</td>
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
