import { describe, it, expect } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useEnrichedRequirements } from './useEnrichedRequirements'

describe('useEnrichedRequirements', () => {
  it('maps latest run per requirement key', () => {
    const reqs = [
      { id: 0, requirement_key: 'REQ-A', description: 'A', function_name: '', requirement_type: 'requirement', supplementary_info: '', is_heading: false, is_info: false },
      { id: 1, requirement_key: 'REQ-B', description: 'B', function_name: '', requirement_type: 'requirement', supplementary_info: '', is_heading: false, is_info: false },
    ]
    const runs = [
      { run_dir: 'old', run_path: '', requirement_key: 'REQ-A', description: '', function_name: '', requirement_count: 1, status: 'new', status_detail: '', created_at: '2025-01-01T00:00:00', is_old_style: false, artifacts: [] },
      { run_dir: 'latest', run_path: '', requirement_key: 'REQ-A', description: '', function_name: '', requirement_count: 1, status: 'evaluated', status_detail: '', created_at: '2026-01-01T00:00:00', is_old_style: false, artifacts: [] },
    ]

    const { result } = renderHook(() => useEnrichedRequirements(reqs, runs))
    const map = result.current

    expect(map.get('REQ-A')).toEqual({
      status: 'evaluated',
      time: '2026-01-01T00:00:00',
      dir: 'latest',
    })
  })

  it('returns empty map when no requirements', () => {
    const { result } = renderHook(() => useEnrichedRequirements(undefined, []))
    expect(result.current.size).toBe(0)
  })

  it('returns empty map when no runs match', () => {
    const reqs = [
      { id: 0, requirement_key: 'REQ-X', description: 'X', function_name: '', requirement_type: 'requirement', supplementary_info: '', is_heading: false, is_info: false },
    ]
    const runs = [
      { run_dir: 'other', run_path: '', requirement_key: 'REQ-Y', description: '', function_name: '', requirement_count: 1, status: 'new', status_detail: '', created_at: '2026-01-01T00:00:00', is_old_style: false, artifacts: [] },
    ]

    const { result } = renderHook(() => useEnrichedRequirements(reqs, runs))
    expect(result.current.has('REQ-X')).toBe(false)
  })
})
