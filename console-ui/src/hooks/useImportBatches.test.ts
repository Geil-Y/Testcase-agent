import { describe, it, expect } from 'vitest'
import { deduplicateBatches } from './useImportBatches'
import type { ImportBatchSummary } from '../api/types'

function makeBatch(overrides: Partial<ImportBatchSummary> = {}): ImportBatchSummary {
  return {
    id: overrides.id || 'batch-1',
    filename: overrides.filename || 'test.xlsx',
    created_at: overrides.created_at || '2026-01-01T00:00:00Z',
    requirements_count: overrides.requirements_count ?? 10,
    ...overrides,
  }
}

describe('deduplicateBatches', () => {
  it('keeps single batch unchanged', () => {
    const batches = [makeBatch()]
    expect(deduplicateBatches(batches)).toHaveLength(1)
  })

  it('deduplicates same-filename batches keeping first occurrence', () => {
    const batches = [
      makeBatch({ id: 'batch-1', filename: 'reqs.xlsx', created_at: '2026-01-02T00:00:00Z' }),
      makeBatch({ id: 'batch-2', filename: 'reqs.xlsx', created_at: '2026-01-01T00:00:00Z' }),
    ]
    const result = deduplicateBatches(batches)
    expect(result).toHaveLength(1)
    expect(result[0].id).toBe('batch-1')
  })

  it('preserves same-name different-id as separate when filename differs', () => {
    const batches = [
      makeBatch({ id: 'batch-1', filename: 'reqs.xlsx' }),
      makeBatch({ id: 'batch-2', filename: 'other.xlsx' }),
    ]
    const result = deduplicateBatches(batches)
    expect(result).toHaveLength(2)
    expect(result.map((b) => b.id).sort()).toEqual(['batch-1', 'batch-2'])
  })

  it('handles multiple duplicates across many filenames', () => {
    const batches = [
      makeBatch({ id: 'a1', filename: 'a.xlsx' }),
      makeBatch({ id: 'a2', filename: 'a.xlsx' }),
      makeBatch({ id: 'b1', filename: 'b.xlsx' }),
      makeBatch({ id: 'b2', filename: 'b.xlsx' }),
      makeBatch({ id: 'c1', filename: 'c.xlsx' }),
    ]
    const result = deduplicateBatches(batches)
    expect(result).toHaveLength(3)
    expect(result.map((b) => b.id).sort()).toEqual(['a1', 'b1', 'c1'])
  })

  it('returns empty array for empty input', () => {
    expect(deduplicateBatches([])).toEqual([])
  })

  it('preserves batch metadata intact', () => {
    const batches = [
      makeBatch({ id: 'batch-1', filename: 'reqs.xlsx', requirements_count: 42 }),
      makeBatch({ id: 'batch-2', filename: 'reqs.xlsx', requirements_count: 99 }),
    ]
    const result = deduplicateBatches(batches)
    expect(result[0].requirements_count).toBe(42)
    expect(result[0].filename).toBe('reqs.xlsx')
  })
})
