import { useEffect, useState, useCallback } from 'react'
import { listImports, getLatestImport, getImportBatch } from '../api/endpoints'
import type { ImportBatch, ImportBatchSummary } from '../api/types'

export function useImportBatches() {
  const [batches, setBatches] = useState<ImportBatchSummary[]>([])
  const [selectedBatch, setSelectedBatch] = useState<ImportBatch | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

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

  return { batches, selectedBatch, loading, error, loadLatest, loadBatch, refetchBatches: fetchBatches }
}
