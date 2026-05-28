import { useEffect, useState, useCallback, useMemo } from 'react'
import { listImports, getLatestImport, getImportBatch } from '../api/endpoints'
import type { ImportBatch, ImportBatchSummary } from '../api/types'

export function deduplicateBatches(batches: ImportBatchSummary[]): ImportBatchSummary[] {
  const seen = new Map<string, ImportBatchSummary>()
  for (const b of batches) {
    const key = b.filename
    if (!seen.has(key)) {
      seen.set(key, b)
    }
  }
  return Array.from(seen.values())
}

export function useImportBatches() {
  const [batches, setBatches] = useState<ImportBatchSummary[]>([])
  const [selectedBatch, setSelectedBatch] = useState<ImportBatch | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const dedupedBatches = useMemo(() => deduplicateBatches(batches), [batches])

  const fetchBatches = useCallback(() => {
    listImports()
      .then((data) => setBatches(data.batches))
      .catch((e) => setError(e.message))
  }, [])

  const loadLatest = useCallback(() => {
    setLoading(true)
    getLatestImport()
      .then(setSelectedBatch)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const loadBatch = useCallback((batchId: string) => {
    setLoading(true)
    getImportBatch(batchId)
      .then(setSelectedBatch)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { fetchBatches() }, [fetchBatches])

  return { batches: dedupedBatches, selectedBatch, loading, error, loadLatest, loadBatch, refetchBatches: fetchBatches }
}
