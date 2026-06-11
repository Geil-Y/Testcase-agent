"""Prompt Learning — shared Python contracts.

These dataclasses mirror the TypeScript types in console-ui/src/api/pl-types.ts
and are the single source of truth for all Prompt Learning backend slices.
"""

from dataclasses import dataclass, field
from typing import Optional

# ── Prompt filenames (the six ABC Pipeline prompt files) ──

LEARNED_PROMPT_FILES: tuple[str, ...] = (
    "analyze_test_basis.system.html",
    "analyze_test_basis.user.html",
    "plan_case_intents.system.html",
    "plan_case_intents.user.html",
    "generate_case.system.html",
    "generate_case.user.html",
)

# ── Workbook inspection ──


@dataclass
class WorkbookSheet:
    """A single sheet found during workbook inspection."""

    name: str
    columns: list[str]  # first-row column headers


@dataclass
class WorkbookInspection:
    """Result of inspecting an Excel workbook for Prompt Learning."""

    filename: str
    sheets: list[WorkbookSheet]


# ── Column mapping (manual, per input type) ──


@dataclass
class RequirementColMap:
    """Manual column mapping for the Requirement Excel sheet."""

    requirement_key: str
    description: str
    function_name: Optional[str] = None
    requirement_type: Optional[str] = None


@dataclass
class RefTestCaseColMap:
    """Manual column mapping for the Reference Test Case Excel sheet."""

    linked_requirements: str
    title: str
    action: str
    expected_result: str
    case_id: Optional[str] = None
    objective: Optional[str] = None


@dataclass
class ColumnMappings:
    """Combined column mappings and sheet selection for a Prompt Learning run."""

    requirement: RequirementColMap
    ref_test_case: RefTestCaseColMap
    ref_test_case_sheets: list[str]


# ── Data issue ──


@dataclass
class DataIssue:
    """A non-fatal data quality issue found during parsing or resolution."""

    file_type: str  # "requirement" | "reference_test_case"
    sheet: str
    row: Optional[int]  # 1-based; None if not row-specific
    issue_type: str  # e.g. "missing_required_field"
    message: str


# ── Parsed input records ──


@dataclass
class ParsedRequirement:
    """A single Requirement row parsed from the Requirement Excel."""

    requirement_key: str
    description: str
    function_name: str = ""
    requirement_type: str = "requirement"
    supplementary_info: dict[str, str] = field(default_factory=dict)
    source_row: int = 0  # 1-based


@dataclass
class ParsedRefTestCase:
    """A single Reference Test Case row parsed from the case Excel."""

    case_id: str  # original or generated sheet-and-row identifier
    case_id_generated: bool  # True when case_id was auto-assigned
    linked_requirements_raw: str  # raw cell text before parsing
    linked_requirement_keys: list[str]  # parsed & normalised keys
    title: str
    title_missing: bool  # True when title was empty in source
    objective: str = ""
    action: str = ""
    expected_result: str = ""
    source_sheet: str = ""
    source_row: int = 0  # 1-based


# ── Resolved learning inputs ──


@dataclass
class ResolvedLink:
    """A single Requirement-to-Reference-Test-Case link after resolution."""

    requirement_key: str
    ref_case_id: str
    resolved: bool  # True when requirement_key matches a known ParsedRequirement


@dataclass
class StyleOnlyCase:
    """A Reference Test Case kept for style-only learning (no resolved links)."""

    case_id: str
    title: str
    source_sheet: str
    source_row: int


@dataclass
class NoTestRequirement:
    """A Requirement with no linked Reference Test Case (likely No-Test)."""

    requirement_key: str
    description: str


# ── Parsed summary ──


@dataclass
class ParsedSummary:
    """Aggregate counts and data issues after parsing + link resolution."""

    requirement_count: int = 0
    ref_test_case_count: int = 0
    valid_link_count: int = 0
    no_test_requirement_count: int = 0
    style_only_case_count: int = 0
    data_issue_count: int = 0
    data_issues: list[DataIssue] = field(default_factory=list)


# ── Learned Prompt Set ──


@dataclass
class LearnedPromptSetMeta:
    """Metadata for one versioned Learned Prompt Set."""

    version: str  # e.g. "2026-06-11T143000"
    created_at: str  # ISO-8601
    provider: str  # e.g. "ollama", "openai"
    model: str  # e.g. "qwen2.5:7b"
    learning_instruction: Optional[str] = None
    summary: ParsedSummary = field(default_factory=ParsedSummary)


@dataclass
class LearnedPromptFile:
    """Contents of a single learned prompt file."""

    filename: str  # one of LEARNED_PROMPT_FILES
    content: str


@dataclass
class LearnedPromptStageGroup:
    """A pair of system + user prompt files for one ABC stage."""

    stage: str  # "A" | "B" | "C"
    stage_label: str
    system_prompt: LearnedPromptFile
    user_prompt: LearnedPromptFile


@dataclass
class LearnedPromptSetVersion:
    """Full contents of one Learned Prompt Set version."""

    meta: LearnedPromptSetMeta
    rationale: str  # rationale.md content
    prompt_groups: list[LearnedPromptStageGroup]


# ── Framework validation ──


@dataclass
class FrameworkValidationError:
    """A single framework validation failure."""

    filename: str
    message: str


@dataclass
class FrameworkValidationResult:
    """Result of validating a learned prompt set against the framework."""

    valid: bool
    errors: list[FrameworkValidationError]
