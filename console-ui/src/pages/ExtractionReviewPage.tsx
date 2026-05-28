import { useState, useCallback } from 'react'
import ExtractionItemEditor from '../components/ExtractionItemEditor'
import ConfirmDialog from '../components/ConfirmDialog'
import { useExtractionReview } from '../hooks/useExtractionReview'
import { useJob } from '../hooks/JobContext'
import type { SectionItem, ExtractionSections } from '../api/types'

interface Props {
  runDir: string
  onAdvanced?: () => void
}

const SECTION_LABELS: Record<keyof ExtractionSections, string> = {
  signals: 'Signals',
  thresholds: 'Thresholds',
  timing: 'Timing',
  states: 'States',
  observations: 'Observations',
}

const SECTION_KEYS = Object.keys(SECTION_LABELS) as (keyof ExtractionSections)[]

let nextTempId = 0
function genTempId(): string {
  nextTempId += 1
  return `new-${Date.now()}-${nextTempId}`
}

export default function ExtractionReviewPage({ runDir, onAdvanced }: Props) {
  const {
    extraction,
    reviewed,
    loading,
    saving,
    error,
    blockingGaps,
    saveReview,
    acceptAll,
    plan,
    refetch,
    isDirty,
    getSectionItems,
    editItem,
    removeItem,
    addItem,
    setBlockingGapsList,
  } = useExtractionReview(runDir)
  const { isLocked, startPolling } = useJob()

  const [statusMsg, setStatusMsg] = useState<string | null>(null)
  const [selectedItem, setSelectedItem] = useState<{ section: keyof ExtractionSections; item: SectionItem } | null>(null)
  const [showAddForm, setShowAddForm] = useState<keyof ExtractionSections | null>(null)
  const [newItem, setNewItem] = useState<Partial<SectionItem>>({})
  const [blockText, setBlockText] = useState('')

  const handleSave = async () => {
    // Save blocking gaps
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
      setStatusMsg('All items accepted. Reviewed extraction saved.')
      refetch()
    } else {
      setStatusMsg((r as { error?: string } | null)?.error || 'Accept all failed')
    }
  }

  const handlePlan = async () => {
    // Save first, then plan
    if (blockText.trim()) {
      setBlockingGapsList(blockText.split('\n').filter(Boolean))
    }
    if (isDirty) {
      await saveReview()
    }
    const raw = await plan()
    if (!raw) return
    const res = raw as Record<string, unknown>
    if (res.status === 'started') {
      startPolling()
      setStatusMsg('Intent planning started...')
    } else {
      setStatusMsg((res.error as string) || 'Plan failed')
    }
  }

  const handleAddItem = (section: keyof ExtractionSections) => {
    if (!newItem.content && !newItem.need) return
    const item: SectionItem = {
      item_id: newItem.item_id || genTempId(),
      status: (newItem.status as SectionItem['status']) || 'known',
      content: newItem.content || '',
      need: newItem.need || '',
      source_text: newItem.source_text || '',
    }
    addItem(section, item)
    setNewItem({})
    setShowAddForm(null)
  }

  if (loading) return <div className="card"><p>Loading extraction data...</p></div>
  if (error) return <div className="error-msg">{error}</div>

  return (
    <div className="extraction-review">
      {statusMsg && (
        <div className="card status-msg">
          {statusMsg}
          <button className="btn btn-sm" onClick={() => setStatusMsg(null)}>Dismiss</button>
        </div>
      )}

      {reviewed && (
        <div className="card" style={{ background: 'rgba(63,185,80,0.1)', border: '1px solid rgba(63,185,80,0.3)', marginBottom: 12 }}>
          <span style={{ color: 'var(--color-success)', fontWeight: 500 }}>This extraction has been reviewed and accepted.</span>
        </div>
      )}

      <div className="review-actions">
        <button className="btn btn-primary" onClick={handleAcceptAll} disabled={isLocked || saving}>
          Accept All
        </button>
        <button className="btn btn-primary" onClick={handleSave} disabled={isLocked || saving || !isDirty}>
          {saving ? 'Saving...' : 'Save Review'}
        </button>
        <button className="btn btn-primary" onClick={handlePlan} disabled={isLocked || saving}>
          Plan Case Intents
        </button>
        <button className="btn btn-sm" onClick={() => { refetch(); setSelectedItem(null); }}>
          Refresh
        </button>
      </div>

      {extraction && (
        <>
          <div className="card" style={{ marginBottom: 16 }}>
            <div className="detail-field">
              <label>Requirement</label>
              <span>{extraction.requirement_key}</span>
            </div>
            {extraction.source_description && (
              <div className="detail-field" style={{ marginTop: 8 }}>
                <label>Source Description</label>
                <div className="affected-text">{extraction.source_description}</div>
              </div>
            )}
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

          {/* Sections */}
          {SECTION_KEYS.map((section) => {
            const items = getSectionItems(section)
            return (
              <div key={section} className="card" style={{ marginBottom: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <h3 style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--color-text)', textTransform: 'capitalize' }}>
                    {SECTION_LABELS[section]} ({items.length})
                  </h3>
                  <button
                    className="btn btn-sm"
                    onClick={() => { setShowAddForm(showAddForm === section ? null : section); setNewItem({}); }}
                  >
                    + Add Item
                  </button>
                </div>

                {/* Add item form */}
                {showAddForm === section && (
                  <div className="card" style={{ marginBottom: 12, background: 'var(--color-bg-elevated)' }}>
                    <div className="detail-grid">
                      <div className="form-group">
                        <label>Item ID</label>
                        <input
                          value={newItem.item_id || ''}
                          onChange={(e) => setNewItem({ ...newItem, item_id: e.target.value })}
                          placeholder="e.g., sig-5"
                        />
                      </div>
                      <div className="form-group">
                        <label>Status</label>
                        <select
                          value={newItem.status || 'known'}
                          onChange={(e) => setNewItem({ ...newItem, status: e.target.value as SectionItem['status'] })}
                        >
                          <option value="known">known</option>
                          <option value="needs_review">needs_review</option>
                        </select>
                      </div>
                      <div className="form-group">
                        <label>Content</label>
                        <textarea
                          value={newItem.content || ''}
                          onChange={(e) => setNewItem({ ...newItem, content: e.target.value })}
                          rows={3}
                        />
                      </div>
                      <div className="form-group">
                        <label>Need</label>
                        <textarea
                          value={newItem.need || ''}
                          onChange={(e) => setNewItem({ ...newItem, need: e.target.value })}
                          rows={2}
                        />
                      </div>
                      <div className="form-group">
                        <label>Source Text</label>
                        <input
                          value={newItem.source_text || ''}
                          onChange={(e) => setNewItem({ ...newItem, source_text: e.target.value })}
                        />
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                      <button className="btn btn-primary btn-sm" onClick={() => handleAddItem(section)}>
                        Add
                      </button>
                      <button className="btn btn-sm" onClick={() => setShowAddForm(null)}>Cancel</button>
                    </div>
                  </div>
                )}

                {/* Items table */}
                {items.length === 0 ? (
                  <p className="text-muted">No items in this section.</p>
                ) : (
                  <div className="queue-list">
                    {items.map((item) => (
                      <button
                        key={`${section}:${item.item_id}`}
                        className={`queue-row ${selectedItem?.section === section && selectedItem?.item.item_id === item.item_id ? 'selected' : ''}`}
                        onClick={() => setSelectedItem({ section, item })}
                      >
                        <span className="queue-item-id">{item.item_id}</span>
                        <span className={`queue-decision ${item.status === 'known' ? 'dec-approve' : 'dec-reject'}`}>
                          {item.status}
                        </span>
                        <span className="queue-type text-muted" style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 200 }}>
                          {item.content?.slice(0, 80)}
                        </span>
                        <button
                          className="btn btn-sm btn-danger"
                          onClick={(e) => { e.stopPropagation(); removeItem(section, item.item_id); }}
                          title="Remove item"
                        >
                          &times;
                        </button>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </>
      )}

      {/* Detail editor for selected item */}
      {selectedItem && (
        <ExtractionItemEditor
          item={selectedItem.item}
          onEdit={(changes) => editItem(selectedItem.section, selectedItem.item.item_id, changes)}
        />
      )}
    </div>
  )
}
