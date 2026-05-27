import { useEffect, useState } from 'react'
import { getResults, exportRun, importMemory } from '../api/endpoints'
import { useJob } from '../hooks/JobContext'
import ConfirmDialog from '../components/ConfirmDialog'
import type { ResultsData } from '../api/types'

interface Props { runDir: string }

export default function ResultsPage({ runDir }: Props) {
  const [data, setData] = useState<ResultsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [memoryConfirm, setMemoryConfirm] = useState(false)
  const [statusMsg, setStatusMsg] = useState<string | null>(null)
  const [expandedCase, setExpandedCase] = useState<number | null>(null)
  const { isLocked } = useJob()

  useEffect(() => {
    getResults(runDir)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [runDir])

  const handleExport = async (includeArchived = false) => {
    try {
      const bundle = await exportRun(runDir, includeArchived)
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = `${runDir}-export.json`; a.click()
      URL.revokeObjectURL(url)
      setStatusMsg('Export complete.')
    } catch {
      setStatusMsg('Export failed.')
    }
  }

  const handleImportMemory = async () => {
    try {
      const res = await importMemory(runDir)
      setStatusMsg(res.message)
    } catch (e: unknown) {
      setStatusMsg(e instanceof Error ? e.message : 'Import failed')
    }
    setMemoryConfirm(false)
  }

  if (loading) return <div className="card"><p>Loading results...</p></div>
  if (error) return <div className="error-msg">{error}</div>
  if (!data) return <div className="error-msg">No results data</div>

  const cases = Array.isArray(data.cases) ? data.cases as Record<string, unknown>[] : []
  const evaluation = data.evaluation as Record<string, unknown> | null

  return (
    <div className="results-page">
      {statusMsg && (
        <div className="card status-msg">
          {statusMsg}
          <button className="btn btn-sm" onClick={() => setStatusMsg(null)}>Dismiss</button>
        </div>
      )}

      <div className="card read-only-notice">
        <strong>Results are read-only.</strong> To change cases, revise upstream review decisions and regenerate.
      </div>

      <div className="results-actions">
        <button className="btn" onClick={() => handleExport(false)} disabled={isLocked}>
          Export (Active)
        </button>
        <button className="btn" onClick={() => handleExport(true)} disabled={isLocked}>
          Export (Include Archived)
        </button>
        <button className="btn" onClick={() => setMemoryConfirm(true)} disabled={isLocked}>
          Import Review Memory
        </button>
      </div>

      {evaluation && (
        <div className="card evaluation-summary">
          <h3>Evaluation</h3>
          {Object.entries(evaluation).map(([k, v]) => (
            <div key={k} className="eval-item">
              <strong>{k}:</strong> {typeof v === 'object' ? JSON.stringify(v) : String(v)}
            </div>
          ))}
        </div>
      )}

      <div className="card">
        <h3>Generated Cases ({cases.length})</h3>
        {cases.map((c, i) => (
          <div key={i} className="case-item">
            <button
              className="case-header"
              onClick={() => setExpandedCase(expandedCase === i ? null : i)}
            >
              <span>{String(c.case_id || `Case ${i + 1}`)}: {String(c.title || 'Untitled')}</span>
              <span>{expandedCase === i ? '▾' : '▸'}</span>
            </button>
            {expandedCase === i && (
              <div className="case-detail">
                {Object.entries(c).map(([k, v]) => (
                  <div key={k} className="case-field">
                    <label>{k}</label>
                    <pre>{typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v)}</pre>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
        {cases.length === 0 && <p className="text-muted">No cases generated yet.</p>}
      </div>

      <ConfirmDialog
        open={memoryConfirm}
        title="Import Review Memory"
        message="Import review decisions from this run into Review Memory? This is an explicit action and will not happen automatically."
        confirmLabel="Import Memory"
        onConfirm={handleImportMemory}
        onCancel={() => setMemoryConfirm(false)}
      />
    </div>
  )
}
