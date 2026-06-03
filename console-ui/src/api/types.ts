export interface Requirement {
  id: number;
  requirement_key: string;
  description: string;
  function_name: string;
  requirement_type: string;
  supplementary_info: string;
  source_row: number;
  imported_at: string;
}

export interface RequirementListResponse {
  items: Requirement[];
  total: number;
}

export interface SectionItem {
  id: number;
  item_id: string;
  status: 'known' | 'needs_review';
  content: string;
  need: string;
  source_text: string;
  sort_order: number;
}

export interface Section {
  section_name: string;
  items: SectionItem[];
}

export interface CaseIntent {
  id: number;
  intent_id: string;
  coverage_dimension: string;
  intent_text: string;
  sort_order: number;
}

export interface TestCaseStep {
  id: number;
  step_order: number;
  action: string;
  expected: string;
}

export interface TestCase {
  id: number;
  title: string;
  objective: string;
  precondition: string;
  postcondition: string;
  raw_html: string;
  sort_order: number;
  intent_id: number | null;
  steps: TestCaseStep[];
  evaluation_items: EvaluationItem[];
}

export interface EvaluationItem {
  id: number;
  item_id: string;
  result: 'pass' | 'fail' | 'warn';
  detail: string;
}

export interface RunDetail {
  run: {
    id: number;
    requirement_id: number;
    status: string;
    review_llm_a: number;
    review_llm_b: number;
    review_llm_c: number;
    error: string | null;
    created_at: string;
    updated_at: string;
  };
  requirement: Requirement;
  sections: Section[];
  intents: CaseIntent[];
  cases: TestCase[];
  evaluation: EvaluationSummary | null;
}

export interface EvaluationSummary {
  total_cases: number;
  passed: number;
  failed: number;
  pass_rate: number;
  cases: CaseEvalResult[];
}

export interface CaseEvalResult {
  case_id: number;
  title: string;
  passed: boolean;
  failed_items: string[];
  warning_items: string[];
}
