import { useEffect, useState, useCallback } from 'react'
import { getRun } from '../api/endpoints'
import type { RunInfo } from '../api/types'

export function useRun(runDir: string | undefined) {
  const [run, setRun] = useState<RunInfo | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetch = useCallback(() => {
    if (!runDir) return
    setLoading(true)
    getRun(runDir)
      .then(setRun)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [runDir])

  useEffect(() => { fetch() }, [fetch])

  return { run, loading, error, refetch: fetch }
}
