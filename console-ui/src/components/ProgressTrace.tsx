import { useEffect, useState } from 'react'
import { getTrace } from '../api/endpoints'
import type { TraceEvent } from '../api/types'

interface Props {
  runDir: string
}

const STAGE_LABELS: Record<string, string> = {
  clarify: 'Clarification',
  intents: 'Case Intents',
  cases: 'Case Generation',
  evaluate: 'Evaluation',
}

const EVENT_ICONS: Record<string, string> = {
  stage_started: '▶',
  llm_call: '◉',
  llm_done: '◎',
  artifact_written: '✔',
  validation: '⚠',
  error: '✖',
  completed: '✔',
  retry: '↻',
}

export default function ProgressTrace({ runDir }: Props) {
  const [events, setEvents] = useState<TraceEvent[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchTrace = () => {
    getTrace(runDir)
      .then((data) => {
        setEvents(data.events)
        setError(null)
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load trace'))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    setLoading(true)
    fetchTrace()
  }, [runDir])

  if (loading) {
    return (
      <div className="card">
        <h3>Progress Trace</h3>
        <p className="text-muted">Loading...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="card">
        <h3>Progress Trace</h3>
        <p className="text-muted">Trace data not available for this run.</p>
      </div>
    )
  }

  if (!events || events.length === 0) {
    return (
      <div className="card">
        <h3>Progress Trace</h3>
        <p className="text-muted">No trace events recorded for this run. This may be an older run created before trace support was added.</p>
      </div>
    )
  }

  return (
    <div className="card">
      <h3>Progress Trace ({events.length} events)</h3>
      <div className="trace-list">
        {events.map((e, i) => (
          <div key={i} className={`trace-event trace-event-${e.event}`}>
            <div className="trace-event-icon">
              {EVENT_ICONS[e.event] || '•'}
            </div>
            <div className="trace-event-body">
              <div className="trace-event-header">
                <span className="trace-stage">{STAGE_LABELS[e.stage] || e.stage}</span>
                <span className="trace-event-type">{e.event}</span>
                {e.duration_ms != null && (
                  <span className="trace-duration">{(e.duration_ms / 1000).toFixed(1)}s</span>
                )}
                <span className="trace-time">{new Date(e.timestamp * 1000).toLocaleTimeString()}</span>
              </div>
              <div className="trace-message">{e.message}</div>
              {(e.provider || e.model) && (
                <div className="trace-meta">
                  {e.provider && <span>{e.provider}</span>}
                  {e.provider && e.model && <span> / </span>}
                  {e.model && <span>{e.model}</span>}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
