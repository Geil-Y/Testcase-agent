import { useEffect, useState, useCallback } from 'react'
import { getMode } from '../api/endpoints'
import type { ConsoleMode } from '../api/types'

export function useMode() {
  const [mode, setMode] = useState<ConsoleMode | null>(null)
  const [error, setError] = useState<string | null>(null)

  const fetch = useCallback(() => {
    getMode()
      .then(setMode)
      .catch((e) => setError(e.message))
  }, [])

  useEffect(() => { fetch() }, [fetch])

  return { mode, error, refetch: fetch }
}
