import { useEffect, useState, useCallback, useRef } from 'react'
import { getCurrentJob } from '../api/endpoints'
import type { JobState, JobStatus } from '../api/types'

interface JobPollState {
  job: JobStatus | null
  status: 'idle' | 'running' | 'succeeded' | 'failed' | 'retryable'
  result: unknown | null
}

export function useJobPolling(pollInterval = 1500) {
  const [state, setState] = useState<JobPollState>({ job: null, status: 'idle', result: null })
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const activeRef = useRef(false)

  const poll = useCallback(() => {
    getCurrentJob()
      .then((data: JobState) => {
        if (data.status === 'active' && data.job) {
          const j = data.job
          if (j.status === 'running') {
            setState({ job: j, status: 'running', result: null })
          } else if (j.status === 'succeeded') {
            stopPolling()
            setState({ job: j, status: 'succeeded', result: j.result ?? null })
          } else if (j.status === 'failed') {
            stopPolling()
            setState({ job: j, status: 'retryable', result: null })
          }
        } else {
          // Check last_job
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
          stopPolling()
        }
      })
      .catch(() => {
        stopPolling()
      })
  }, [])

  const startPolling = useCallback(() => {
    if (activeRef.current) return
    activeRef.current = true
    poll()
    intervalRef.current = setInterval(poll, pollInterval)
  }, [poll, pollInterval])

  const stopPolling = useCallback(() => {
    activeRef.current = false
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
  }, [])

  const clear = useCallback(() => {
    stopPolling()
    setState({ job: null, status: 'idle', result: null })
  }, [stopPolling])

  useEffect(() => {
    return () => stopPolling()
  }, [stopPolling])

  return { ...state, startPolling, stopPolling, clear, poll, isLocked: state.status === 'running' }
}
