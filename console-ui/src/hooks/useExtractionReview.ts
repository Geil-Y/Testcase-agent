import { useEffect, useState, useCallback } from 'react'
import {
  getExtraction,
  acceptAllExtraction,
  saveExtractionReview,
  planIntents,
} from '../api/endpoints'
import type {
  ExtractedTestBasis,
  SectionItem,
  ExtractionReviewAction,
} from '../api/types'

const SECTION_KEYS = ['signals', 'thresholds', 'timing', 'states', 'observations'] as const
type SectionKey = typeof SECTION_KEYS[number]

export function useExtractionReview(runDir: string | undefined) {
  const [extraction, setExtraction] = useState<ExtractedTestBasis | null>(null)
  const [reviewed, setReviewed] = useState(false)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Track edits: keyed by `${section}:${item_id}`
  const [edits, setEdits] = useState<Map<string, Partial<SectionItem>>>(new Map())
  // Track removed items: set of `${section}:${item_id}`
  const [removed, setRemoved] = useState<Set<string>>(new Set())
  // Track added items: Map of `${section}:${tempId}` -> SectionItem
  const [added, setAdded] = useState<Map<string, SectionItem>>(new Map())
  // Blocking gaps text
  const [blockingGaps, setBlockingGaps] = useState<string[]>([])

  const load = useCallback(() => {
    if (!runDir) return
    setLoading(true)
    setError(null)
    getExtraction(runDir)
      .then((data) => {
        setExtraction(data.extraction)
        setReviewed(data.reviewed)
        setBlockingGaps(data.extraction.blocking_gaps || [])
        setEdits(new Map())
        setRemoved(new Set())
        setAdded(new Map())
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [runDir])

  useEffect(() => { load() }, [load])

  // Get current items for a section (original + added - removed, with edits applied)
  const getSectionItems = useCallback((section: SectionKey): SectionItem[] => {
    if (!extraction) return []
    const original = extraction.sections[section] || []

    // Start with original items not in removed set
    const result = original
      .filter((item) => !removed.has(`${section}:${item.item_id}`))
      .map((item) => {
        const edit = edits.get(`${section}:${item.item_id}`)
        return edit ? { ...item, ...edit } : item
      })

    // Add new items
    for (const [key, item] of added) {
      if (key.startsWith(`${section}:`)) {
        result.push(item)
      }
    }

    return result
  }, [extraction, edits, removed, added])

  // Edit an existing item
  const editItem = useCallback((section: SectionKey, itemId: string, changes: Partial<SectionItem>) => {
    const key = `${section}:${itemId}`
    setEdits((prev) => {
      const next = new Map(prev)
      const current = next.get(key) || {}
      next.set(key, { ...current, ...changes })
      return next
    })
  }, [])

  // Remove an existing item
  const removeItem = useCallback((section: SectionKey, itemId: string) => {
    const key = `${section}:${itemId}`
    setRemoved((prev) => new Set([...prev, key]))
    // If it was added, remove from added instead
    if (added.has(key)) {
      setAdded((prev) => {
        const next = new Map(prev)
        next.delete(key)
        return next
      })
      setRemoved((prev) => {
        const next = new Set(prev)
        next.delete(key)
        return next
      })
    }
  }, [added])

  // Add a new item to a section
  const addItem = useCallback((section: SectionKey, item: SectionItem) => {
    const key = `${section}:${item.item_id}`
    setAdded((prev) => new Map(prev).set(key, item))
  }, [])

  // Set blocking gaps
  const setBlockingGapsList = useCallback((gaps: string[]) => {
    setBlockingGaps(gaps)
  }, [])

  const isDirty =
    edits.size > 0 ||
    removed.size > 0 ||
    added.size > 0 ||
    JSON.stringify(blockingGaps) !== JSON.stringify(extraction?.blocking_gaps || [])

  // Build review actions from current state
  const buildActions = useCallback((): ExtractionReviewAction[] => {
    const actions: ExtractionReviewAction[] = []

    // Edits
    for (const [key, changes] of edits) {
      const [section, itemId] = key.split(':')
      actions.push({
        item_id: itemId,
        section,
        action: 'edit',
        changes,
      })
    }

    // Removals (only for original items, not added ones)
    for (const key of removed) {
      const [section, itemId] = key.split(':')
      if (!added.has(key)) {
        actions.push({
          item_id: itemId,
          section,
          action: 'remove',
        })
      }
    }

    // Additions
    for (const [key, newItem] of added) {
      const [section] = key.split(':')
      actions.push({
        item_id: newItem.item_id,
        section,
        action: 'add',
        new_item: newItem,
      })
    }

    // Blocking gaps
    if (blockingGaps.length > 0) {
      actions.push({
        item_id: 'blocking_gaps',
        section: '_meta',
        action: 'block',
        changes: { blocking_gaps: blockingGaps },
      } as ExtractionReviewAction)
    }

    return actions
  }, [edits, removed, added, blockingGaps])

  const saveReview = useCallback(async () => {
    if (!runDir) return { success: false, error: 'No run' }
    setSaving(true)
    try {
      const actions = buildActions()
      const res = await saveExtractionReview(runDir, actions)
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
      const res = await acceptAllExtraction(runDir)
      return res
    } catch (e: unknown) {
      return { saved: false, error: e instanceof Error ? e.message : 'Accept all failed' }
    } finally {
      setSaving(false)
    }
  }, [runDir])

  const plan = useCallback(async () => {
    if (!runDir) return null
    setSaving(true)
    try {
      return await planIntents(runDir)
    } catch (e: unknown) {
      return { status: 'error', error: e instanceof Error ? e.message : 'Plan failed' }
    } finally {
      setSaving(false)
    }
  }, [runDir])

  return {
    extraction,
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
    plan,
    refetch: load,
    isDirty,
    getSectionItems,
    editItem,
    removeItem,
    addItem,
    setBlockingGapsList,
  }
}
