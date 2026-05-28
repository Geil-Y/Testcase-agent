import { useEffect, useState, useCallback } from 'react'
import { getCases, acceptAllCases, editCases, exportRun } from '../api/endpoints'
import { useJob } from '../hooks/JobContext'
import RegenerateDialog from '../components/RegenerateDialog'
import type { CasesResponse, GeneratedCase, CaseEditRequest } from '../api/types'

interface Props { runDir: string }

export default function ResultsPage({ runDir }: Props) {
  const [data, setData] = useState<CasesResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusMsg, setStatusMsg] = useState<string | null>(null)
  const [expandedCase, setExpandedCase] = useState<string | null>(null)

  // Editing state
  const [editingCaseId, setEditingCaseId] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState<Partial<GeneratedCase>>({})
  const [saving, setSaving] = useState(false)

  // Regenerate state
  const [regenCase, setRegenCase] = useState<{ caseId: string; intentId: string } | null>(null)

  const { isLocked, startPolling } = useJob()

  const load = useCallback(() => {
    setLoading(true)
    getCases(runDir)
      .then((d) => {
        setData(d)
        setError(null)
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [runDir])

  useEffect(() => { load() }, [load])

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

  const handleAcceptAll = async () => {
    setSaving(true)
    try {
      const res = await acceptAllCases(runDir)
      if (res.saved) {
        setStatusMsg('All cases accepted.')
        load()
      }
    } catch (e: unknown) {
      setStatusMsg(e instanceof Error ? e.message : 'Accept all failed')
    } finally {
      setSaving(false)
    }
  }

  const startEditing = (c: GeneratedCase) => {
    setEditingCaseId(c.case_id)
    setEditDraft({
      title: c.title,
      objective: c.objective,
      pre_condition: c.pre_condition,
      steps: [...(c.steps || [])],
      post_condition: c.post_condition,
    })
  }

  const cancelEditing = () => {
    setEditingCaseId(null)
    setEditDraft({})
  }

  const handleSaveEdit = async (caseId: string) => {
    setSaving(true)
    try {
      const edits: CaseEditRequest[] = [{ case_id: caseId, changes: editDraft }]
      const res = await editCases(runDir, edits)
      if (res.saved) {
        setStatusMsg('Case saved.')
        setEditingCaseId(null)
        setEditDraft({})
        load()
      }
    } catch (e: unknown) {
      setStatusMsg(e instanceof Error ? e.message : 'Edit failed')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div className="card"><p>Loading cases...</p></div>
  if (error) return <div className="error-msg">{error}</div>
  if (!data) return <div className="error-msg">No cases data</div>

  const cases = data.cases?.cases || []
  const reviewed = data.reviewed

  return (
    <div className="results-page">
      {statusMsg && (
        <div className="card status-msg">
          {statusMsg}
          <button className="btn btn-sm" onClick={() => setStatusMsg(null)}>Dismiss</button>
        </div>
      )}

      {reviewed && (
        <div className="card" style={{ background: 'rgba(63,185,80,0.1)', border: '1px solid rgba(63,185,80,0.3)', marginBottom: 12 }}>
          <span style={{ color: 'var(--color-success)', fontWeight: 500 }}>Cases have been reviewed and accepted.</span>
        </div>
      )}

      <div className="card read-only-notice">
        <strong>Edit or regenerate cases as needed.</strong> Accept all when complete.
      </div>

      <div className="results-actions">
        <button className="btn btn-primary" onClick={handleAcceptAll} disabled={isLocked || saving}>
          Accept All
        </button>
        <button className="btn" onClick={() => handleExport(false)} disabled={isLocked}>
          Export (Active)
        </button>
        <button className="btn" onClick={() => handleExport(true)} disabled={isLocked}>
          Export (Include Archived)
        </button>
        <button className="btn btn-sm" onClick={load}>Refresh</button>
      </div>

      <div className="card">
        <h3>Generated Cases ({cases.length})</h3>
        {cases.map((c) => (
          <div key={c.case_id} className="case-item">
            <button
              className="case-header"
              onClick={() => setExpandedCase(expandedCase === c.case_id ? null : c.case_id)}
            >
              <span>{c.case_id}: {c.title || 'Untitled'}</span>
              <span>{expandedCase === c.case_id ? '▾' : '▸'}</span>
            </button>
            {expandedCase === c.case_id && (
              <div className="case-detail">
                {editingCaseId === c.case_id ? (
                  <>
                    <div className="detail-grid">
                      <div className="form-group">
                        <label>Title</label>
                        <input
                          value={editDraft.title || ''}
                          onChange={(e) => setEditDraft({ ...editDraft, title: e.target.value })}
                        />
                      </div>
                      <div className="form-group">
                        <label>Objective</label>
                        <textarea
                          value={editDraft.objective || ''}
                          onChange={(e) => setEditDraft({ ...editDraft, objective: e.target.value })}
                          rows={3}
                        />
                      </div>
                      <div className="form-group">
                        <label>Pre-condition</label>
                        <textarea
                          value={editDraft.pre_condition || ''}
                          onChange={(e) => setEditDraft({ ...editDraft, pre_condition: e.target.value })}
                          rows={2}
                        />
                      </div>
                      <div className="form-group">
                        <label>Post-condition</label>
                        <textarea
                          value={editDraft.post_condition || ''}
                          onChange={(e) => setEditDraft({ ...editDraft, post_condition: e.target.value })}
                          rows={2}
                        />
                      </div>
                      <div className="form-group">
                        <label>Steps (one per line)</label>
                        <textarea
                          value={(editDraft.steps || []).join('\n')}
                          onChange={(e) => setEditDraft({ ...editDraft, steps: e.target.value.split('\n') })}
                          rows={6}
                        />
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                      <button
                        className="btn btn-primary btn-sm"
                        onClick={() => handleSaveEdit(c.case_id)}
                        disabled={saving}
                      >
                        {saving ? 'Saving...' : 'Save'}
                      </button>
                      <button className="btn btn-sm" onClick={cancelEditing}>Cancel</button>
                    </div>
                  </>
                ) : (
                  <>
                    {Object.entries(c).map(([k, v]) => (
                      <div key={k} className="case-field">
                        <label>{k}</label>
                        <pre>{typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v)}</pre>
                      </div>
                    ))}
                    <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                      <button className="btn btn-sm" onClick={() => startEditing(c)}>
                        Edit
                      </button>
                      <button
                        className="btn btn-sm btn-danger"
                        onClick={() => setRegenCase({ caseId: c.case_id, intentId: c.intent_id || '' })}
                      >
                        Regenerate
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        ))}
        {cases.length === 0 && <p className="text-muted">No cases generated yet.</p>}
      </div>

      {regenCase && (
        <RegenerateDialog
          open={!!regenCase}
          runDir={runDir}
          caseId={regenCase.caseId}
          intentId={regenCase.intentId}
          onClose={() => setRegenCase(null)}
          onStarted={startPolling}
        />
      )}
    </div>
  )
}
