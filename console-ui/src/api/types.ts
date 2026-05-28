// ── Console API response types (simplified ABC pipeline) ──────────────────

export interface ImportBatchSummary {
  id: string
  filename: string
  created_at: string
  requirements_count: number
  column_mapping?: Record<string, unknown>
}

export interface Requirement {
  id: number
  requirement_key: string
  description: string
  function_name: string
  requirement_type: string
  supplementary_info: string
  is_heading: boolean
  is_info: boolean
  latest_run_status?: string
  latest_run_time?: string
  latest_run_dir?: string
}

export interface ImportBatch {
  id: string
  filename: string
  created_at: string
  requirements_count: number
  column_mapping?: Record<string, unknown>
  requirements: Requirement[]
}

export interface ConsoleMode {
  provider: string
  model: string
  mode: 'mock' | 'real'
  label: string
  is_mock: boolean
}

export interface JobStatus {
  id: string
  name: string
  status: 'queued' | 'running' | 'succeeded' | 'failed'
  created_at: number
  started_at: number | null
  finished_at: number | null
  has_result: boolean
  error: string | null
  error_detail: string | null
  run_dir: string | null
  result?: unknown
}

export interface JobState {
  status: 'idle' | 'active'
  job?: JobStatus
  last_job?: JobStatus
}

export interface RunInfo {
  run_dir: string
  run_path: string
  requirement_key: string
  description: string
  function_name: string
  requirement_count: number
  status: string
  status_detail: string
  created_at: string
  is_old_style: boolean
  artifacts: string[]
}

export interface ValidationErrorItem {
  artifact_path?: string
  field_path?: string
  item_id?: string
  message: string
}

export interface ArtifactSummary {
  stage: string
  upstream_artifact: string
  affected_artifacts: string[]
  message: string
}

// ── Extraction (Stage A) ──────────────────────────────────────────────────

export interface SectionItem {
  item_id: string
  status: 'known' | 'unknown' | 'assumed'
  content: string
  need: string
  source_text: string
}

export interface ExtractionSections {
  signals: SectionItem[]
  thresholds: SectionItem[]
  timing: SectionItem[]
  states: SectionItem[]
  observations: SectionItem[]
}

export interface ExtractedTestBasis {
  requirement_key: string
  source_description: string
  sections: ExtractionSections
  blocking_gaps: string[]
}

export interface ExtractionResponse {
  run: RunInfo
  extraction: ExtractedTestBasis
  reviewed: boolean
}

// ── Case Intents (Stage B) ────────────────────────────────────────────────

export interface CaseIntent {
  intent_id: string
  coverage_dimension: string
  intent_text: string
}

export interface CaseIntentSet {
  requirement_key: string
  intents: CaseIntent[]
  blocking_gaps: string[]
}

export interface IntentsResponse {
  run: RunInfo
  intents: CaseIntentSet
  reviewed: boolean
}

// ── Cases (Stage C) ───────────────────────────────────────────────────────

export interface GeneratedCase {
  case_id: string
  title: string
  objective: string
  pre_condition: string
  steps: string[]
  post_condition: string
  requirement_key: string
  intent_id: string
  coverage_dimension: string
}

export interface GeneratedCaseSet {
  requirement_key: string
  cases: GeneratedCase[]
}

export interface CasesResponse {
  run: RunInfo
  cases: GeneratedCaseSet
  reviewed: boolean
}

// ── Review Actions ────────────────────────────────────────────────────────

export interface ExtractionReviewAction {
  item_id: string
  section: string
  action: 'edit' | 'add' | 'remove' | 'block'
  changes?: Partial<SectionItem>
  new_item?: SectionItem
}

export interface IntentReviewAction {
  intent_id: string
  action: 'edit' | 'add' | 'remove' | 'block'
  changes?: Partial<CaseIntent>
  new_intent?: CaseIntent
}

export interface CaseEditRequest {
  case_id: string
  changes: Partial<GeneratedCase>
}

export interface CaseRegenerateRequest {
  case_id: string
  intent_id: string
  review_comment: string
}

export interface PreviewResult {
  filename: string
  sheets: string[]
  columns: string[]
  tmp_path: string
}

export interface TraceEvent {
  timestamp: number
  stage: string
  event: string
  provider?: string | null
  model?: string | null
  duration_ms?: number | null
  message: string
  detail?: string | null
}

export interface TraceData {
  run_dir: string
  events: TraceEvent[]
}

export interface ExportBundle {
  run: RunInfo
  active_artifacts: Record<string, unknown>
  archived_artifacts: unknown[]
}
