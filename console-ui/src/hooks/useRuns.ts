import { useEffect, useState, useCallback } from 'react'
import { listRuns } from '../api/endpoints'
import type { RunInfo } from '../api/types'

export function useRuns() {
  const [runs, setRuns] = useState<RunInfo[]>([])
  const [error, setError] = useState<string | null>(null)

  const fetch = useCallback(() => {
    listRuns()
      .then((data) => setRuns(data.runs))
      .catch((e) => setError(e.message))
  }, [])

  useEffect(() => { fetch() }, [fetch])

  return { runs, error, refetch: fetch }
}
