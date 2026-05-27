import { useState, useCallback } from 'react'
import ReviewQueue from '../components/ReviewQueue'
import ClarificationDetail from '../components/ClarificationDetail'
import ValidationSummary from '../components/ValidationSummary'
import ConfirmDialog from '../components/ConfirmDialog'
import { useClarificationReview } from '../hooks/useClarificationReview'
import { useJob } from '../hooks/JobContext'

interface Props {
  runDir: string
}

export default function ClarificationReviewPage({ runDir }: Props) {
  const {
    items, selectedId, selectedItem, loading, saving, error,
    reasonCodes, memoryHints, validationErrors,
    setSelectedId, updateDraftItem, saveDraft, advance, acceptRecs,
    applyProposedDecisions, setFilterParams, filters, isDirty, refetch,
    setValidationErrors,
  } = useClarificationReview(runDir)
  const { isLocked, startPolling } = useJob()

  const [decisionFilter, setDecisionFilter] = useState('')
  const [routingFilter, setRoutingFilter] = useState('')
  const [search, setSearch] = useState('')
  const [highRiskConfirm, setHighRiskConfirm] = useState(false)
  const [statusMsg, setStatusMsg] = useState<string | null>(null)

  const handleFilter = useCallback((field: string, value: string) => {
    if (field === 'decision') setDecisionFilter(value)
    if (field === 'routing') setRoutingFilter(value)
    if (field === 'search') setSearch(value)
    setFilterParams({
      decision_filter: field === 'decision' ? value : decisionFilter,
      routing_filter: field === 'routing' ? value : routingFilter,
      search: field === 'search' ? value : search,
      sort: 'priority',
    })
  }, [setFilterParams, decisionFilter, routingFilter, search])

  const handleAcceptRecs = async () => {
    const result = await acceptRecs(false)
    if (!result) return
    if (result.requires_confirmation) {
      setHighRiskConfirm(true)
    } else if (result.proposed_decisions) {
      applyProposedDecisions(result.proposed_decisions)
      setStatusMsg(result.message)
    }
  }

  const handleHighRiskConfirm = async () => {
    const result = await acceptRecs(true)
    if (result && result.proposed_decisions) {
      applyProposedDecisions(result.proposed_decisions)
      setStatusMsg(result.message)
    }
    setHighRiskConfirm(false)
  }

  const handleSaveDraft = async () => {
    const result = await saveDraft()
    if (result && result.success) {
      setStatusMsg('Draft saved.')
      refetch()
      setValidationErrors(new Map())
    } else {
      setStatusMsg((result as { error?: string } | null)?.error || 'Save failed')
    }
  }

  const handleAdvance = async () => {
    const raw = await advance()
    if (!raw) return
    const res = raw as Record<string, unknown>
    if (res.status === 'started') {
      startPolling()
      setStatusMsg('Clarification advance started...')
    } else if (res.validated === false && res.errors) {
      const errMap = new Map<string, string[]>()
      for (const e of (res.errors as Array<Record<string, unknown>>)) {
        const id = String(e.item_id || 'unknown')
        const msgs = errMap.get(id) || []
        msgs.push(String(e.message || ''))
        errMap.set(id, msgs)
      }
      setValidationErrors(errMap)
      setStatusMsg('Validation failed. Fix errors below.')
    } else if (res.blocked) {
      const reasons = Array.isArray(res.block_reasons) ? res.block_reasons : []
      setStatusMsg('Run is blocked: ' + reasons.join(', '))
    } else {
      setStatusMsg('Advanced to Case Intent Review!')
      refetch()
    }
  }

  if (loading) return <div className="card"><p>Loading clarification review...</p></div>
  if (error) return <div className="error-msg">{error}</div>

  const itemErrors = selectedId ? validationErrors.get(selectedId) || [] : []

  return (
    <div className="clarification-review">
      {statusMsg && (
        <div className="card status-msg">
          {statusMsg}
          <button className="btn btn-sm" onClick={() => setStatusMsg(null)}>Dismiss</button>
        </div>
      )}

      <ValidationSummary
        errors={validationErrors}
        onSelectItem={(id) => setSelectedId(id)}
      />

      <div className="review-actions">
        <button
          className="btn"
          onClick={handleAcceptRecs}
          disabled={isLocked || loading}
        >
          Accept Recommendations
        </button>
        <button
          className="btn btn-primary"
          onClick={handleSaveDraft}
          disabled={isLocked || saving || !isDirty}
        >
          {saving ? 'Saving...' : 'Save Draft'}
        </button>
        <button
          className="btn btn-primary"
          onClick={handleAdvance}
          disabled={isLocked || saving || !isDirty}
        >
          Save &amp; Prepare Case Intent Review
        </button>
        <button className="btn btn-sm" onClick={() => { refetch(); setValidationErrors(new Map()); }}>
          Refresh
        </button>
      </div>

      <div className="review-body">
        <ReviewQueue
          items={items}
          selectedId={selectedId}
          onSelect={setSelectedId}
          validationErrors={validationErrors}
          decisionFilter={decisionFilter}
          routingFilter={routingFilter}
          search={search}
          onDecisionFilter={(v) => handleFilter('decision', v)}
          onRoutingFilter={(v) => handleFilter('routing', v)}
          onSearch={(v) => handleFilter('search', v)}
        />

        <ClarificationDetail
          item={selectedItem}
          reasonCodes={reasonCodes}
          memoryHints={memoryHints}
          validationErrors={itemErrors}
          onChange={(changes) => selectedId && updateDraftItem(selectedId, changes)}
        />
      </div>

      <ConfirmDialog
        open={highRiskConfirm}
        title="High-Risk Items"
        message="Some items have orange/red confidence. Are you sure you want to accept all recommendations?"
        confirmLabel="Accept All"
        danger
        onConfirm={handleHighRiskConfirm}
        onCancel={() => setHighRiskConfirm(false)}
      />
    </div>
  )
}
