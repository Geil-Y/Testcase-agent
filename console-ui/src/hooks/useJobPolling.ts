import { useEffect, useState, useCallback, useRef } from 'react'
import { getCurrentJob } from '../api/endpoints'
import type { JobState, JobStatus } from '../api/types'

interface JobPollState {
  job: JobStatus | null
  status: 'idle' | 'running' | 'succeeded' | 'failed' | 'retryable'
  result: unknown | null
}

function clearIntervalSafe(ref: React.MutableRefObject<ReturnType<typeof setInterval> | null>) {
  if (ref.current) {
    clearInterval(ref.current)
    ref.current = null
  }
}

export function useJobPolling(pollInterval = 1500) {
  const [state, setState] = useState<JobPollState>({ job: null, status: 'idle', result: null })
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopPolling = useCallback(() => {
    clearIntervalSafe(intervalRef)
  }, [])

  const poll = useCallback(() => {
    getCurrentJob()
      .then((data: JobState) => {
        if (data.status === 'active' && data.job) {
          const j = data.job
          if (j.status === 'running') {
            setState({ job: j, status: 'running', result: null })
          } else if (j.status === 'succeeded') {
            clearIntervalSafe(intervalRef)
            setState({ job: j, status: 'succeeded', result: j.result ?? null })
          } else if (j.status === 'failed') {
            clearIntervalSafe(intervalRef)
            setState({ job: j, status: 'retryable', result: null })
          }
        } else {
          const last = (data as JobState).last_job
          if (last) {
            if (last.status === 'succeeded') {
              setState({ job: last, status: 'succeeded', result: last.result ?? null })
            } else if (last.status === 'failed') {
              setState({ job: last, status: 'retryable', result: null })
            } else {
              setState({ job: null, status: 'idle', result: null })
            }
          } else {
            setState({ job: null, status: 'idle', result: null })
          }
          clearIntervalSafe(intervalRef)
        }
      })
      .catch(() => {
        clearIntervalSafe(intervalRef)
      })
  }, [])

  const startPolling = useCallback(() => {
    if (intervalRef.current) return // already polling
    poll()
    intervalRef.current = setInterval(poll, pollInterval)
  }, [poll, pollInterval])

  const clear = useCallback(() => {
    stopPolling()
    setState({ job: null, status: 'idle', result: null })
  }, [stopPolling])

  useEffect(() => {
    return () => stopPolling()
  }, [stopPolling])

  return { ...state, startPolling, stopPolling, clear, poll, isLocked: state.status === 'running' }
}
