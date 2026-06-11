/**
 * Prompt Learning — shared TypeScript contracts.
 *
 * These types are the single source of truth for all Prompt Learning slices:
 * workbook inspection, column mapping, parsing, link resolution, storage,
 * validation, API transport, and UI display.
 */

// ── Prompt filenames (the six ABC Pipeline prompt files) ──

export const LEARNED_PROMPT_FILES = [
  'analyze_test_basis.system.html',
  'analyze_test_basis.user.html',
  'plan_case_intents.system.html',
  'plan_case_intents.user.html',
  'generate_case.system.html',
  'generate_case.user.html',
] as const;

export type LearnedPromptFileName = (typeof LEARNED_PROMPT_FILES)[number];

// ── Workbook inspection ──

export interface WorkbookSheet {
  /** Sheet tab name in the Excel workbook. */
  name: string;
  /** First-row column headers found in this sheet. */
  columns: string[];
}

export interface WorkbookInspection {
  /** Source filename (not full path). */
  filename: string;
  /** Sheets found in the workbook. */
  sheets: WorkbookSheet[];
}

// ── Column mapping (manual, per input type) ──

export type RequirementColMap = {
  /** Column name for the requirement key. */
  requirementKey: string;
  /** Column name for the requirement description. */
  description: string;
  /** Optional column for function name. */
  functionName?: string;
  /** Optional column for requirement type. */
  requirementType?: string;
};

export type RefTestCaseColMap = {
  /** Column name for the case identifier (may be empty if absent). */
  caseId?: string;
  /** Column name holding linked requirement identifiers. */
  linkedRequirements: string;
  /** Column name for the case title. */
  title: string;
  /** Column name for the action / test steps. */
  action: string;
  /** Column name for the expected result. */
  expectedResult: string;
  /** Optional column for objective. */
  objective?: string;
};

export interface ColumnMappings {
  requirement: RequirementColMap;
  refTestCase: RefTestCaseColMap;
  /** Sheet names selected from the Reference Test Case workbook. */
  refTestCaseSheets: string[];
}

// ── Data issue ──

export interface DataIssue {
  /** "requirement" | "reference_test_case" */
  fileType: string;
  /** Sheet name where the issue was found. */
  sheet: string;
  /** 1-based row number in the sheet, or null if not row-specific. */
  row: number | null;
  /** Machine-readable issue type (e.g. "missing_required_field"). */
  issueType: string;
  /** Human-readable description. */
  message: string;
}

// ── Parsed input records ──

export interface ParsedRequirement {
  requirementKey: string;
  description: string;
  functionName: string;
  requirementType: string;
  supplementaryInfo: Record<string, string>;
  /** 1-based source row in the Excel sheet. */
  sourceRow: number;
}

export interface ParsedRefTestCase {
  /** Original case id, or a temporary sheet-and-row identifier if missing. */
  caseId: string;
  /** Whether caseId was auto-generated (missing in source). */
  caseIdGenerated: boolean;
  /** Raw linked requirement identifiers text (before parsing). */
  linkedRequirementsRaw: string;
  /** Parsed and normalised requirement identifiers. */
  linkedRequirementKeys: string[];
  title: string;
  /** True when the title was empty in the source row. */
  titleMissing: boolean;
  objective: string;
  action: string;
  expectedResult: string;
  sourceSheet: string;
  /** 1-based source row in the Excel sheet. */
  sourceRow: number;
}

// ── Resolved learning inputs ──

export interface ResolvedLink {
  requirementKey: string;
  refCaseId: string;
  /** True when the link resolved to a known parsed Requirement. */
  resolved: boolean;
}

/** A Reference Test Case that has no resolved Requirement links —
 *  kept for style-only learning. */
export interface StyleOnlyCase {
  caseId: string;
  title: string;
  sourceSheet: string;
  sourceRow: number;
}

/** A Requirement that has no linked Reference Test Case —
 *  treated as a likely No-Test example. */
export interface NoTestRequirement {
  requirementKey: string;
  description: string;
}

// ── Parsed summary ──

export interface ParsedSummary {
  requirementCount: number;
  refTestCaseCount: number;
  /** Number of valid Requirement-to-Ref-Test-Case links. */
  validLinkCount: number;
  /** Requirements with zero linked Reference Test Cases. */
  noTestRequirementCount: number;
  /** Reference Test Cases kept for style only (no resolved links). */
  styleOnlyCaseCount: number;
  dataIssueCount: number;
  dataIssues: DataIssue[];
}

// ── Learned Prompt Set ──

export interface LearnedPromptSetMeta {
  /** Version folder name, e.g. "2026-06-11T143000". */
  version: string;
  /** ISO-8601 creation timestamp. */
  createdAt: string;
  /** LLM provider name used during learning (e.g. "ollama", "openai"). */
  provider: string;
  /** LLM model name used during learning (e.g. "qwen2.5:7b"). */
  model: string;
  /** Optional free-text instruction that guided this learning run. */
  learningInstruction?: string;
  /** Parsed-input summary counts (no full asset content). */
  summary: ParsedSummary;
}

/** Contents of a single learned prompt file (read-only display). */
export interface LearnedPromptFile {
  filename: LearnedPromptFileName;
  content: string;
}

/** Grouped prompt files by ABC stage for UI display. */
export interface LearnedPromptStageGroup {
  stage: 'A' | 'B' | 'C';
  stageLabel: string;
  systemPrompt: LearnedPromptFile;
  userPrompt: LearnedPromptFile;
}

/** Full contents of one Learned Prompt Set version. */
export interface LearnedPromptSetVersion {
  meta: LearnedPromptSetMeta;
  /** rationale.md content (may be empty string). */
  rationale: string;
  /** Prompt files grouped by LLM-A / LLM-B / LLM-C. */
  promptGroups: LearnedPromptStageGroup[];
}

/** Lightweight version list entry (no file contents). */
export type LearnedPromptSetListItem = LearnedPromptSetMeta;

// ── Framework validation ──

export interface FrameworkValidationError {
  filename: string;
  message: string;
}

export interface FrameworkValidationResult {
  valid: boolean;
  errors: FrameworkValidationError[];
}
