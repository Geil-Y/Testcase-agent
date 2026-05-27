import { useEffect, useState, useCallback } from 'react'
import { getIntentReview, saveIntentDraft, generateCases, getReasonCodes } from '../api/endpoints'
import type { IntentReviewItem, ReasonCodes } from '../api/types'

export function useIntentReview(runDir: string | undefined) {
  const [items, setItems] = useState<IntentReviewItem[]>([])
  const [draft, setDraft] = useState<Map<string, IntentReviewItem>>(new Map())
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [reasonCodes, setReasonCodes] = useState<ReasonCodes | null>(null)
  const [validationErrors, setValidationErrors] = useState<Map<string, string[]>>(new Map())

  const load = useCallback(() => {
    if (!runDir) return
    setLoading(true)
    getIntentReview(runDir)
      .then((data) => {
        const decisions = data.review?.decisions || []
        setItems(decisions)
        const d = new Map<string, IntentReviewItem>()
        for (const item of decisions) {
          if (item.decision) d.set(item.intent_id, { ...item })
        }
        setDraft(d)
        if (decisions.length > 0 && !selectedId) setSelectedId(decisions[0].intent_id)
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [runDir, selectedId])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    if (!runDir) return
    getReasonCodes('case_intent').then(setReasonCodes).catch(() => {})
  }, [runDir])

  const updateDraftItem = useCallback((intentId: string, changes: Partial<IntentReviewItem>) => {
    setDraft((prev) => {
      const next = new Map(prev)
      const current = next.get(intentId) || items.find((i) => i.intent_id === intentId) || { intent_id: intentId } as IntentReviewItem
      next.set(intentId, { ...current, ...changes })
      return next
    })
  }, [items])

  const selectedItem = selectedId
    ? (draft.get(selectedId) || items.find((i) => i.intent_id === selectedId) || null)
    : null

  const isDirty = draft.size > 0

  const saveDraft = useCallback(async () => {
    if (!runDir) return { success: false, error: 'No run' }
    setSaving(true)
    try {
      const decisions = Array.from(draft.values())
      await saveIntentDraft(runDir, decisions)
      return { success: true }
    } catch (e: unknown) {
      return { success: false, error: e instanceof Error ? e.message : 'Save failed' }
    } finally {
      setSaving(false)
    }
  }, [runDir, draft])

  const generate = useCallback(async () => {
    if (!runDir) return null
    setSaving(true)
    try {
      const decisions = Array.from(draft.values())
      return await generateCases(runDir, decisions)
    } catch (e: unknown) {
      return { status: 'error', error: e instanceof Error ? e.message : 'Generation failed' }
    } finally {
      setSaving(false)
    }
  }, [runDir, draft])

  return {
    items, draft, selectedId, selectedItem, loading, saving, error,
    reasonCodes, validationErrors, filters: {} as Record<string, string>,
    setSelectedId, updateDraftItem, saveDraft, generate,
    setFilterParams: () => {}, refetch: () => load(),
    isDirty, setValidationErrors,
  }
}
