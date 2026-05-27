import { useEffect, useState, useCallback } from 'react'
import {
  getFilteredClarification,
  saveClarificationDraft,
  advanceClarification,
  acceptRecommendations,
  getReasonCodes,
  getMemoryHints,
} from '../api/endpoints'
import type { ReviewItem, ReasonCodes, MemoryHints, AcceptRecommendationsResult } from '../api/types'

interface FilterParams {
  decision_filter?: string
  routing_filter?: string
  search?: string
  sort?: string
}

export function useClarificationReview(runDir: string | undefined) {
  const [items, setItems] = useState<ReviewItem[]>([])
  const [draft, setDraft] = useState<Map<string, ReviewItem>>(new Map())
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [reasonCodes, setReasonCodes] = useState<ReasonCodes | null>(null)
  const [memoryHints, setMemoryHints] = useState<MemoryHints | null>(null)
  const [validationErrors, setValidationErrors] = useState<Map<string, string[]>>(new Map())
  const [filters, setFilters] = useState<FilterParams>({ sort: 'priority' })

  const load = useCallback((params?: FilterParams) => {
    if (!runDir) return
    setLoading(true)
    const p = params || filters
    getFilteredClarification(runDir, p)
      .then((data) => {
        const decisions = data.review?.decisions || []
        setItems(decisions)
        // Init draft from server decisions
        const d = new Map<string, ReviewItem>()
        for (const item of decisions) {
          if (item.decision) {
            d.set(item.item_id, { ...item })
          }
        }
        setDraft(d)
        if (decisions.length > 0 && !selectedId) {
          setSelectedId(decisions[0].item_id)
        }
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [runDir, filters, selectedId])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    if (!runDir) return
    getReasonCodes('clarification').then(setReasonCodes).catch(() => {})
    getMemoryHints(runDir).then(setMemoryHints).catch(() => {})
  }, [runDir])

  const updateDraftItem = useCallback((itemId: string, changes: Partial<ReviewItem>) => {
    setDraft((prev) => {
      const next = new Map(prev)
      const current = next.get(itemId) || items.find((i) => i.item_id === itemId) || { item_id: itemId } as ReviewItem
      next.set(itemId, { ...current, ...changes })
      return next
    })
  }, [items])

  const selectedItem = selectedId
    ? (draft.get(selectedId) || items.find((i) => i.item_id === selectedId) || null)
    : null

  const isDirty = draft.size > 0

  const saveDraft = useCallback(async () => {
    if (!runDir) return
    setSaving(true)
    try {
      const decisions = Array.from(draft.values())
      await saveClarificationDraft(runDir, decisions)
      return { success: true }
    } catch (e: unknown) {
      return { success: false, error: e instanceof Error ? e.message : 'Save failed' }
    } finally {
      setSaving(false)
    }
  }, [runDir, draft])

  const advance = useCallback(async () => {
    if (!runDir) return
    setSaving(true)
    try {
      const decisions = Array.from(draft.values())
      const res = await advanceClarification(runDir, decisions)
      return res
    } catch (e: unknown) {
      return { status: 'error', error: e instanceof Error ? e.message : 'Advance failed' }
    } finally {
      setSaving(false)
    }
  }, [runDir, draft])

  const acceptRecs = useCallback(async (confirm = false): Promise<AcceptRecommendationsResult | null> => {
    if (!runDir) return null
    try {
      return await acceptRecommendations(runDir, confirm)
    } catch {
      return null
    }
  }, [runDir])

  const applyProposedDecisions = useCallback((proposed: { item_id: string; decision: string }[]) => {
    for (const p of proposed) {
      updateDraftItem(p.item_id, { decision: p.decision })
    }
  }, [updateDraftItem])

  const setFilterParams = useCallback((params: FilterParams) => {
    setFilters(params)
    load(params)
  }, [load])

  return {
    items, draft, selectedId, selectedItem, loading, saving, error,
    reasonCodes, memoryHints, validationErrors, filters,
    setSelectedId, updateDraftItem, saveDraft, advance, acceptRecs,
    applyProposedDecisions, setFilterParams, refetch: () => load(),
    isDirty,
    setValidationErrors,
  }
}
