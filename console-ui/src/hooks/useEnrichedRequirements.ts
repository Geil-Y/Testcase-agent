import { useMemo } from 'react'
import type { Requirement, RunInfo } from '../api/types'

export interface RunSummary {
  status: string
  time: string
  dir: string
}

export function useEnrichedRequirements(
  requirements: Requirement[] | undefined,
  runs: RunInfo[],
): Map<string, RunSummary> {
  return useMemo(() => {
    const map = new Map<string, RunSummary>()
    if (!requirements) return map

    // Build a map of requirement_key → latest run
    const runsByReq = new Map<string, RunInfo>()
    for (const r of runs) {
      const key = r.requirement_key
      const existing = runsByReq.get(key)
      if (!existing || r.created_at > existing.created_at) {
        runsByReq.set(key, r)
      }
    }

    for (const req of requirements) {
      const run = runsByReq.get(req.requirement_key)
      if (run) {
        map.set(req.requirement_key, {
          status: run.status,
          time: run.created_at,
          dir: run.run_dir,
        })
      }
    }

    return map
  }, [requirements, runs])
}
