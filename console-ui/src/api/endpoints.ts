// ── Typed endpoint functions (simplified ABC pipeline) ───────────────────

import { get, post, upload } from './client'
import type {
  ImportBatch,
  ImportBatchSummary,
  ConsoleMode,
  JobState,
  RunInfo,
  ExtractionResponse,
  IntentsResponse,
  CasesResponse,
  PreviewResult,
  ExportBundle,
  ValidationErrorItem,
  TraceData,
  ExtractionReviewAction,
  IntentReviewAction,
  CaseEditRequest,
  CaseRegenerateRequest,
} from './types'

// Imports
export const listImports = () => get<{ batches: ImportBatchSummary[] }>('/imports')
export const getLatestImport = () => get<ImportBatch>('/imports/latest')
export const getImportBatch = (batchId: string) => get<ImportBatch>(`/imports/${batchId}`)
export const previewExcel = (file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return upload<PreviewResult>('/imports/preview', fd)
}
export const confirmImport = (data: Record<string, unknown>) =>
  post<ImportBatch>('/imports/confirm', data)

// Mode
export const getMode = () => get<ConsoleMode>('/mode')

// Jobs
export const getCurrentJob = () => get<JobState>('/jobs/current')
export const checkJobRunning = () => get<{ running: boolean }>('/jobs/is-running')
export const retryJob = () => post<{ status: string; job: JobState['job'] }>('/jobs/retry')

// Runs
export const listRuns = () => get<{ runs: RunInfo[] }>('/runs')
export const getRun = (runDir: string) => get<RunInfo>(`/runs/${runDir}`)
export const startRun = (data: { requirement_key: string; batch_id: string }) =>
  post<{ status: string; job: JobState['job'] }>('/runs/start', data)

// ── Extraction (Stage A) ─────────────────────────────────────────────────

export const getExtraction = (runDir: string) =>
  get<ExtractionResponse>(`/runs/${runDir}/extraction`)

export const acceptAllExtraction = (runDir: string) =>
  post<{ saved: boolean; run: RunInfo }>(`/runs/${runDir}/extraction/accept-all`)

export const saveExtractionReview = (runDir: string, actions: ExtractionReviewAction[]) =>
  post<{ saved: boolean; run: RunInfo }>(`/runs/${runDir}/extraction/review`, { actions })

// ── Case Intents (Stage B) ───────────────────────────────────────────────

export const planIntents = (runDir: string) =>
  post<{ status: string; job: JobState['job'] }>(`/runs/${runDir}/intents/plan`)

export const getIntents = (runDir: string) =>
  get<IntentsResponse>(`/runs/${runDir}/intents`)

export const acceptAllIntents = (runDir: string) =>
  post<{ saved: boolean; run: RunInfo }>(`/runs/${runDir}/intents/accept-all`)

export const saveIntentReview = (runDir: string, actions: IntentReviewAction[]) =>
  post<{ saved: boolean; run: RunInfo }>(`/runs/${runDir}/intents/review`, { actions })

// ── Cases (Stage C) ──────────────────────────────────────────────────────

export const generateCases = (runDir: string) =>
  post<{ status: string; job: JobState['job'] }>(`/runs/${runDir}/cases/generate`)

export const getCases = (runDir: string) =>
  get<CasesResponse>(`/runs/${runDir}/cases`)

export const acceptAllCases = (runDir: string) =>
  post<{ saved: boolean; run: RunInfo }>(`/runs/${runDir}/cases/accept-all`)

export const editCases = (runDir: string, edits: CaseEditRequest[]) =>
  post<{ saved: boolean; run: RunInfo }>(`/runs/${runDir}/cases/edit`, { edits })

export const regenerateCase = (runDir: string, requests: CaseRegenerateRequest[]) =>
  post<{ status: string; job: JobState['job'] }>(`/runs/${runDir}/cases/regenerate`, { requests })

// Trace
export const getTrace = (runDir: string) => get<TraceData>(`/runs/${runDir}/trace`)

// Export
export const exportRun = (runDir: string, includeArchived = false) =>
  get<ExportBundle>(`/runs/${runDir}/export?include_archived=${includeArchived}`)

// Re-export validation error type
export type { ValidationErrorItem }
