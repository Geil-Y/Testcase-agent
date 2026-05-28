import { useState, useCallback } from 'react'
import { useIntentReview } from '../hooks/useIntentReview'
import { useJob } from '../hooks/JobContext'
import type { CaseIntent } from '../api/types'

interface Props { runDir: string }

const COVERAGE_DIMENSIONS = [
  'normal_behavior',
  'boundary',
  'error_handling',
  'edge_case',
  'performance',
  'safety',
  'interaction',
]

let nextTempId = 0
function genTempId(): string {
  nextTempId += 1
  return `intent-new-${Date.now()}-${nextTempId}`
}

export default function IntentReviewPage({ runDir }: Props) {
  const {
    intents,
    reviewed,
    loading,
    saving,
    error,
    blockingGaps,
    saveReview,
    acceptAll,
    generate,
    refetch,
    isDirty,
    getCurrentIntents,
    editIntent,
    removeIntent,
    addIntent,
    setBlockingGapsList,
  } = useIntentReview(runDir)
  const { isLocked, startPolling } = useJob()

  const [statusMsg, setStatusMsg] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [showAddForm, setShowAddForm] = useState(false)
  const [newIntent, setNewIntent] = useState<Partial<CaseIntent>>({
    coverage_dimension: 'normal_behavior',
    intent_text: '',
  })
  const [blockText, setBlockText] = useState('')

  const handleSaveReview = async () => {
    if (blockText.trim()) {
      setBlockingGapsList(blockText.split('\n').filter(Boolean))
    }
    const r = await saveReview()
    setStatusMsg(r?.success ? 'Review saved.' : (r as { error?: string })?.error || 'Save failed')
    if (r?.success) refetch()
  }

  const handleAcceptAll = async () => {
    const r = await acceptAll()
    if (r?.saved) {
      setStatusMsg('All intents accepted. Reviewed intents saved.')
      refetch()
    } else {
      setStatusMsg((r as { error?: string } | null)?.error || 'Accept all failed')
    }
  }

  const handleGenerate = async () => {
    if (blockText.trim()) {
      setBlockingGapsList(blockText.split('\n').filter(Boolean))
    }
    if (isDirty) {
      await saveReview()
    }
    const raw = await generate()
    if (!raw) return
    const res = raw as Record<string, unknown>
    if (res.status === 'started') {
      startPolling()
      setStatusMsg('Case generation started...')
    } else if (res.validated === false && res.errors) {
      setStatusMsg('Validation failed.')
    } else {
      setStatusMsg('Cases generated!')
      refetch()
    }
  }

  const handleAddIntent = () => {
    if (!newIntent.intent_text?.trim()) return
    const intent: CaseIntent = {
      intent_id: newIntent.intent_id || genTempId(),
      coverage_dimension: newIntent.coverage_dimension || 'normal_behavior',
      intent_text: newIntent.intent_text,
    }
    addIntent(intent)
    setNewIntent({ coverage_dimension: 'normal_behavior', intent_text: '' })
    setShowAddForm(false)
  }

  if (loading) return <div className="card"><p>Loading case intents...</p></div>
  if (error) return <div className="error-msg">{error}</div>

  const items = getCurrentIntents()
  const selectedItem = items.find((i) => i.intent_id === selectedId) || null

  return (
    <div className="intent-review">
      {statusMsg && (
        <div className="card status-msg">
          {statusMsg}
          <button className="btn btn-sm" onClick={() => setStatusMsg(null)}>Dismiss</button>
        </div>
      )}

      {reviewed && (
        <div className="card" style={{ background: 'rgba(63,185,80,0.1)', border: '1px solid rgba(63,185,80,0.3)', marginBottom: 12 }}>
          <span style={{ color: 'var(--color-success)', fontWeight: 500 }}>Case intents have been reviewed and accepted.</span>
        </div>
      )}

      <div className="review-actions">
        <button className="btn btn-primary" onClick={handleAcceptAll} disabled={isLocked || saving}>
          Accept All
        </button>
        <button className="btn btn-primary" onClick={handleSaveReview} disabled={isLocked || saving || !isDirty}>
          {saving ? 'Saving...' : 'Save Review'}
        </button>
        <button className="btn btn-primary" onClick={handleGenerate} disabled={isLocked || saving}>
          Generate Cases
        </button>
        <button className="btn btn-sm" onClick={() => refetch()}>
          Refresh
        </button>
      </div>

      {intents && (
        <>
          <div className="card" style={{ marginBottom: 16 }}>
            <div className="detail-field">
              <label>Requirement</label>
              <span>{intents.requirement_key}</span>
            </div>
          </div>

          {/* Blocking Gaps */}
          <div className="card" style={{ marginBottom: 16 }}>
            <h3 style={{ fontSize: '0.875rem', marginBottom: 8 }}>Blocking Gaps</h3>
            <textarea
              value={blockText || blockingGaps.join('\n')}
              onChange={(e) => setBlockText(e.target.value)}
              rows={3}
              placeholder="Enter blocking gaps (one per line)..."
            />
          </div>

          {/* Add Intent */}
          <div className="card" style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <h3 style={{ fontSize: '0.875rem', fontWeight: 500 }}>Case Intents ({items.length})</h3>
              <button
                className="btn btn-sm"
                onClick={() => { setShowAddForm(!showAddForm); setNewIntent({ coverage_dimension: 'normal_behavior', intent_text: '' }); }}
              >
                + Add Intent
              </button>
            </div>

            {showAddForm && (
              <div className="card" style={{ marginBottom: 12, background: 'var(--color-bg-elevated)' }}>
                <div className="detail-grid">
                  <div className="form-group">
                    <label>Intent ID</label>
                    <input
                      value={newIntent.intent_id || ''}
                      onChange={(e) => setNewIntent({ ...newIntent, intent_id: e.target.value })}
                      placeholder="e.g., intent-5"
                    />
                  </div>
                  <div className="form-group">
                    <label>Coverage Dimension</label>
                    <select
                      value={newIntent.coverage_dimension || 'normal_behavior'}
                      onChange={(e) => setNewIntent({ ...newIntent, coverage_dimension: e.target.value })}
                    >
                      {COVERAGE_DIMENSIONS.map((d) => (
                        <option key={d} value={d}>{d}</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label>Intent Text</label>
                    <textarea
                      value={newIntent.intent_text || ''}
                      onChange={(e) => setNewIntent({ ...newIntent, intent_text: e.target.value })}
                      rows={3}
                      placeholder="Describe the test intent..."
                    />
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                  <button className="btn btn-primary btn-sm" onClick={handleAddIntent}>
                    Add
                  </button>
                  <button className="btn btn-sm" onClick={() => setShowAddForm(false)}>Cancel</button>
                </div>
              </div>
            )}
          </div>
        </>
      )}

      <div className="review-body">
        <div className="review-queue">
          <div className="queue-list">
            {items.length === 0 && <p className="text-muted">No intents yet.</p>}
            {items.map((item) => (
              <button
                key={item.intent_id}
                className={`queue-row ${item.intent_id === selectedId ? 'selected' : ''}`}
                onClick={() => setSelectedId(item.intent_id)}
              >
                <span className="queue-item-id">{item.intent_id}</span>
                <span className="queue-type text-muted">{item.coverage_dimension}</span>
                <button
                  className="btn btn-sm btn-danger"
                  onClick={(e) => { e.stopPropagation(); removeIntent(item.intent_id); if (selectedId === item.intent_id) setSelectedId(null); }}
                  title="Remove intent"
                >
                  &times;
                </button>
              </button>
            ))}
          </div>
        </div>

        {/* Intent detail editor */}
        <div className="card review-detail">
          {selectedItem ? (
            <>
              <h3>{selectedItem.intent_id}</h3>
              <div className="detail-grid">
                <div className="form-group">
                  <label>Coverage Dimension</label>
                  <select
                    value={selectedItem.coverage_dimension || 'normal_behavior'}
                    onChange={(e) => editIntent(selectedItem.intent_id, { coverage_dimension: e.target.value })}
                  >
                    {COVERAGE_DIMENSIONS.map((d) => (
                      <option key={d} value={d}>{d}</option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label>Intent Text</label>
                  <textarea
                    value={selectedItem.intent_text || ''}
                    onChange={(e) => editIntent(selectedItem.intent_id, { intent_text: e.target.value })}
                    rows={5}
                  />
                </div>
              </div>
            </>
          ) : (
            <p className="text-muted">Select an intent to edit.</p>
          )}
        </div>
      </div>
    </div>
  )
}
