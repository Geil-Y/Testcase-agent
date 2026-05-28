import { useEffect, useState, useCallback } from 'react'
import { getIntents, saveIntentReview, acceptAllIntents, generateCases } from '../api/endpoints'
import type { CaseIntent, CaseIntentSet, IntentReviewAction } from '../api/types'

export function useIntentReview(runDir: string | undefined) {
  const [intents, setIntents] = useState<CaseIntentSet | null>(null)
  const [reviewed, setReviewed] = useState(false)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Track edits: keyed by intent_id
  const [edits, setEdits] = useState<Map<string, Partial<CaseIntent>>>(new Map())
  // Track removed intents: set of intent_id
  const [removed, setRemoved] = useState<Set<string>>(new Set())
  // Track added intents
  const [added, setAdded] = useState<CaseIntent[]>([])
  // Blocking gaps
  const [blockingGaps, setBlockingGaps] = useState<string[]>([])

  const load = useCallback(() => {
    if (!runDir) return
    setLoading(true)
    setError(null)
    getIntents(runDir)
      .then((data) => {
        setIntents(data.intents)
        setReviewed(data.reviewed)
        setBlockingGaps(data.intents.blocking_gaps || [])
        setEdits(new Map())
        setRemoved(new Set())
        setAdded([])
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [runDir])

  useEffect(() => { load() }, [load])

  // Get current intents (original + added - removed, with edits applied)
  const getCurrentIntents = useCallback((): CaseIntent[] => {
    if (!intents) return []
    const original = intents.intents || []

    const result = original
      .filter((item) => !removed.has(item.intent_id))
      .map((item) => {
        const edit = edits.get(item.intent_id)
        return edit ? { ...item, ...edit } : item
      })

    for (const item of added) {
      result.push(item)
    }

    return result
  }, [intents, edits, removed, added])

  const editIntent = useCallback((intentId: string, changes: Partial<CaseIntent>) => {
    setEdits((prev) => {
      const next = new Map(prev)
      const current = next.get(intentId) || {}
      next.set(intentId, { ...current, ...changes })
      return next
    })
  }, [])

  const removeIntent = useCallback((intentId: string) => {
    setRemoved((prev) => new Set([...prev, intentId]))
    // If it was added, remove from added instead
    setAdded((prev) => prev.filter((i) => i.intent_id !== intentId))
  }, [])

  const addIntent = useCallback((intent: CaseIntent) => {
    setAdded((prev) => [...prev, intent])
  }, [])

  const setBlockingGapsList = useCallback((gaps: string[]) => {
    setBlockingGaps(gaps)
  }, [])

  const isDirty =
    edits.size > 0 || removed.size > 0 || added.length > 0 ||
    JSON.stringify(blockingGaps) !== JSON.stringify(intents?.blocking_gaps || [])

  const buildActions = useCallback((): IntentReviewAction[] => {
    const actions: IntentReviewAction[] = []

    for (const [intentId, changes] of edits) {
      actions.push({ intent_id: intentId, action: 'edit', changes })
    }

    for (const intentId of removed) {
      actions.push({ intent_id: intentId, action: 'remove' })
    }

    for (const newIntent of added) {
      actions.push({ intent_id: newIntent.intent_id, action: 'add', new_intent: newIntent })
    }

    if (blockingGaps.length > 0) {
      actions.push({ intent_id: 'blocking_gaps', action: 'block' })
    }

    return actions
  }, [edits, removed, added, blockingGaps])

  const saveReview = useCallback(async () => {
    if (!runDir) return { success: false, error: 'No run' }
    setSaving(true)
    try {
      const actions = buildActions()
      const res = await saveIntentReview(runDir, actions)
      return { success: res.saved }
    } catch (e: unknown) {
      return { success: false, error: e instanceof Error ? e.message : 'Save failed' }
    } finally {
      setSaving(false)
    }
  }, [runDir, buildActions])

  const acceptAll = useCallback(async () => {
    if (!runDir) return null
    setSaving(true)
    try {
      const res = await acceptAllIntents(runDir)
      return res
    } catch (e: unknown) {
      return { saved: false, error: e instanceof Error ? e.message : 'Accept all failed' }
    } finally {
      setSaving(false)
    }
  }, [runDir])

  const generate = useCallback(async () => {
    if (!runDir) return null
    setSaving(true)
    try {
      return await generateCases(runDir)
    } catch (e: unknown) {
      return { status: 'error', error: e instanceof Error ? e.message : 'Generation failed' }
    } finally {
      setSaving(false)
    }
  }, [runDir])

  return {
    intents,
    reviewed,
    loading,
    saving,
    error,
    edits,
    removed,
    added,
    blockingGaps,
    saveReview,
    acceptAll,
    generate,
    refetch: load,
    isDirty,
    getCurrentIntents,
    editIntent,
    removeIntent,
    addIntent,
    setBlockingGapsList,
  }
}
