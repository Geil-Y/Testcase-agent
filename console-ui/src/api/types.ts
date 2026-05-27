// ── Console API response types ───────────────────────────────────────────

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

export interface ReviewDecision {
  item_id?: string
  intent_id?: string
  decision: string
  reason_codes?: string[]
  reason_text?: string
  clarified_value?: string
  edited_content?: Record<string, unknown>
  revised_intent_text?: string
  merge_target_id?: string
  split_children?: unknown[]
}

export interface ReviewItem {
  item_id: string
  decision: string
  reason_codes: string[]
  reason_text: string
  clarified_value: string
  edited_content: Record<string, unknown>
  ambiguity_type?: string
  recommended_decision?: string
  routing_color?: string
  affected_text?: string
  impact?: string
  severity?: string
  clarification_question?: string
  confidence_drivers?: Record<string, number>
  [key: string]: unknown
}

export interface ClarificationReview {
  run: RunInfo
  review: {
    decisions: ReviewItem[]
    decomposition?: {
      facts?: unknown[]
      ambiguities?: unknown[]
    }
    [key: string]: unknown
  }
}

export interface IntentReviewItem {
  intent_id: string
  decision: string
  reason_codes: string[]
  reason_text: string
  revised_intent_text: string
  merge_target_id: string
  split_children: unknown[]
  coverage_dimension?: string
  intent_text?: string
  routing_color?: string
  recommended_decision?: string
  confidence_drivers?: Record<string, number>
  [key: string]: unknown
}

export interface IntentReview {
  run: RunInfo
  review: {
    decisions: IntentReviewItem[]
    [key: string]: unknown
  }
}

export interface ResultsData {
  run: RunInfo
  cases: unknown | null
  evaluation: unknown | null
  evaluation_detail: unknown | null
  read_only: boolean
  note: string
}

export interface ReasonCodes {
  review_type: string
  decisions: string[]
  reason_codes: Record<string, string[]>
  decision_requirements: Record<string, { requires_reason_code: boolean; requires_reason_text: boolean }>
}

export interface MemoryHints {
  run: string
  hints: string[]
  adjustment: number
  advisory_note: string
}

export interface AcceptRecommendationsResult {
  proposed_decisions: { item_id: string; decision: string }[]
  filled: number
  high_risk_skipped?: number
  high_risk_accepted?: number
  high_risk_items?: string[]
  requires_confirmation: boolean
  saved: boolean
  message: string
}

export interface PreviewResult {
  filename: string
  sheets: string[]
  columns: string[]
  tmp_path: string
}

export interface ExportBundle {
  run: RunInfo
  active_artifacts: Record<string, unknown>
  archived_artifacts: unknown[]
}
