// ── Typed endpoint functions ──────────────────────────────────────────────

import { get, post, upload } from './client'
import type {
  ImportBatch,
  ImportBatchSummary,
  ConsoleMode,
  JobState,
  RunInfo,
  ClarificationReview,
  IntentReview,
  ResultsData,
  ReasonCodes,
  MemoryHints,
  AcceptRecommendationsResult,
  PreviewResult,
  ExportBundle,
  ValidationErrorItem,
  ArtifactSummary,
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

// Clarification Review
export const getClarificationReview = (runDir: string) =>
  get<ClarificationReview>(`/runs/${runDir}/clarification`)
export const getFilteredClarification = (
  runDir: string,
  params: { decision_filter?: string; routing_filter?: string; search?: string; sort?: string }
) => {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => { if (v) qs.set(k, v) })
  return get<ClarificationReview & { filters: Record<string, string>; total: number }>(
    `/runs/${runDir}/clarification/filtered?${qs}`
  )
}
export const saveClarificationDraft = (runDir: string, decisions: unknown[]) =>
  post<{ saved: boolean; run: RunInfo }>(`/runs/${runDir}/clarification/draft`, { decisions })
export const advanceClarification = (runDir: string, decisions: unknown[]) =>
  post<{ status: string; job: JobState['job'] }>(`/runs/${runDir}/clarification/advance`, { decisions })
export const acceptRecommendations = (runDir: string, confirmHighRisk = false) =>
  post<AcceptRecommendationsResult>(`/runs/${runDir}/clarification/accept-recommendations`, {
    confirm_high_risk: confirmHighRisk,
  })

// Reason Codes
export const getReasonCodes = (reviewType = 'clarification') =>
  get<ReasonCodes>(`/reason-codes?review_type=${reviewType}`)

// Memory Hints
export const getMemoryHints = (runDir: string) => get<MemoryHints>(`/runs/${runDir}/memory-hints`)

// Case Intent Review
export const getIntentReview = (runDir: string) => get<IntentReview>(`/runs/${runDir}/intents`)
export const saveIntentDraft = (runDir: string, decisions: unknown[]) =>
  post<{ saved: boolean; run: RunInfo }>(`/runs/${runDir}/intents/draft`, { decisions })
export const generateCases = (runDir: string, decisions: unknown[]) =>
  post<{ status: string; job: JobState['job'] }>(`/runs/${runDir}/intents/generate`, { decisions })

// Results
export const getResults = (runDir: string) => get<ResultsData>(`/runs/${runDir}/results`)
export const downloadArtifact = (runDir: string, artifactName: string) =>
  get<{ artifact: string; content: unknown }>(`/runs/${runDir}/artifacts/${artifactName}`)
export const exportRun = (runDir: string, includeArchived = false) =>
  get<ExportBundle>(`/runs/${runDir}/export?include_archived=${includeArchived}`)
export const importMemory = (runDir: string) =>
  post<{ imported: boolean; run: string; message: string }>(`/runs/${runDir}/import-memory`)

// Regenerate
export const regenerateConfirm = (runDir: string, stage: string) =>
  post<ArtifactSummary & { confirmation_required: boolean }>(`/runs/${runDir}/regenerate`, { stage, confirm: false })
export const regenerateExecute = (runDir: string, stage: string) =>
  post<{ status: string; job: JobState['job']; archived: string[] }>(`/runs/${runDir}/regenerate`, { stage, confirm: true })

// Re-export validation error type
export type { ValidationErrorItem }
