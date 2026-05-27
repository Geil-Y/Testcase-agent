import { createContext, useContext, type ReactNode } from 'react'
import { useJobPolling } from './useJobPolling'

type JobContextType = ReturnType<typeof useJobPolling>

const JobContext = createContext<JobContextType | null>(null)

export function JobProvider({ children }: { children: ReactNode }) {
  const jobState = useJobPolling()
  return <JobContext.Provider value={jobState}>{children}</JobContext.Provider>
}

export function useJob() {
  const ctx = useContext(JobContext)
  if (!ctx) throw new Error('useJob must be used within JobProvider')
  return ctx
}
