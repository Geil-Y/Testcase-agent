/**
 * Type-level and shape checks for Prompt Learning contracts.
 *
 * These tests verify that the contracts defined in pl-types.ts are internally
 * consistent so that later slices (parser, resolver, storage, UI) consume
 * compatible shapes.
 */

import { describe, it, expect } from 'vitest';
import {
  LEARNED_PROMPT_FILES,
  type LearnedPromptFileName,
  type WorkbookInspection,
  type WorkbookSheet,
  type ColumnMappings,
  type DataIssue,
  type ParsedRequirement,
  type ParsedRefTestCase,
  type ResolvedLink,
  type StyleOnlyCase,
  type NoTestRequirement,
  type ParsedSummary,
  type LearnedPromptSetMeta,
  type LearnedPromptSetVersion,
  type LearnedPromptStageGroup,
  type FrameworkValidationResult,
} from './pl-types';

describe('LEARNED_PROMPT_FILES constant', () => {
  it('contains exactly six files', () => {
    expect(LEARNED_PROMPT_FILES).toHaveLength(6);
  });

  it('has exactly one system and one user file per ABC stage', () => {
    const stages = new Set(LEARNED_PROMPT_FILES.map(f => f.split('.')[0]));
    // Three unique stage prefixes: analyze_test_basis, plan_case_intents, generate_case
    expect(stages.size).toBe(3);
    expect(stages.has('analyze_test_basis')).toBe(true);
    expect(stages.has('plan_case_intents')).toBe(true);
    expect(stages.has('generate_case')).toBe(true);
  });

  it('every stage has both a .system.html and .user.html variant', () => {
    const stages = ['analyze_test_basis', 'plan_case_intents', 'generate_case'];
    for (const stage of stages) {
      expect(LEARNED_PROMPT_FILES).toContain(`${stage}.system.html`);
      expect(LEARNED_PROMPT_FILES).toContain(`${stage}.user.html`);
    }
  });

  it('all filenames end with .html', () => {
    for (const f of LEARNED_PROMPT_FILES) {
      expect(f.endsWith('.html')).toBe(true);
    }
  });
});

describe('WorkbookInspection shape', () => {
  it('accepts valid workbook inspection data', () => {
    const inspection: WorkbookInspection = {
      filename: 'requirements.xlsx',
      sheets: [
        { name: 'Sheet1', columns: ['A', 'B', 'C'] },
      ],
    };
    expect(inspection.sheets[0].name).toBe('Sheet1');
    expect(inspection.sheets[0].columns).toEqual(['A', 'B', 'C']);
  });
});

describe('ColumnMappings shape', () => {
  it('accepts full column mappings with optional fields', () => {
    const mappings: ColumnMappings = {
      requirement: {
        requirementKey: 'Req_ID',
        description: 'Description',
        functionName: 'Func',
      },
      refTestCase: {
        caseId: 'Case_ID',
        linkedRequirements: 'Req_ID',
        title: 'Title',
        action: 'Action',
        expectedResult: 'Expected',
        objective: 'Obj',
      },
      refTestCaseSheets: ['Sheet1'],
    };
    expect(mappings.requirement.requirementKey).toBe('Req_ID');
    expect(mappings.refTestCaseSheets).toHaveLength(1);
  });

  it('accepts minimal column mappings (optional fields omitted)', () => {
    const mappings: ColumnMappings = {
      requirement: {
        requirementKey: 'ID',
        description: 'Desc',
      },
      refTestCase: {
        linkedRequirements: 'Req_ID',
        title: 'Title',
        action: 'Steps',
        expectedResult: 'Expected',
      },
      refTestCaseSheets: ['S1', 'S2'],
    };
    expect(mappings.requirement.functionName).toBeUndefined();
    expect(mappings.refTestCase.caseId).toBeUndefined();
  });
});

describe('DataIssue shape', () => {
  it('accepts a data issue with a row number', () => {
    const issue: DataIssue = {
      fileType: 'requirement',
      sheet: 'Sheet1',
      row: 5,
      issueType: 'missing_required_field',
      message: 'Missing requirement key at row 5',
    };
    expect(issue.row).toBe(5);
  });

  it('accepts a data issue with null row', () => {
    const issue: DataIssue = {
      fileType: 'reference_test_case',
      sheet: 'Cases',
      row: null,
      issueType: 'empty_sheet',
      message: 'Sheet has no usable rows',
    };
    expect(issue.row).toBeNull();
  });
});

describe('ParsedRequirement shape', () => {
  it('accepts parsed requirement with supplementary info', () => {
    const req: ParsedRequirement = {
      requirementKey: 'REQ-001',
      description: 'Cell overvoltage protection',
      functionName: 'OVP',
      requirementType: 'requirement',
      supplementaryInfo: { extra_col: 'value' },
      sourceRow: 3,
    };
    expect(req.supplementaryInfo['extra_col']).toBe('value');
  });
});

describe('ParsedRefTestCase shape', () => {
  it('accepts parsed reference test case with linked requirements', () => {
    const rtc: ParsedRefTestCase = {
      caseId: 'TC-001',
      caseIdGenerated: false,
      linkedRequirementsRaw: 'REQ-001\nREQ-002',
      linkedRequirementKeys: ['REQ-001', 'REQ-002'],
      title: 'Verify overvoltage cutoff',
      titleMissing: false,
      objective: 'Ensure safety',
      action: '1. Set voltage\n2. Measure output',
      expectedResult: 'Output shuts off within 100ms',
      sourceSheet: 'Cases',
      sourceRow: 5,
    };
    expect(rtc.linkedRequirementKeys).toHaveLength(2);
  });

  it('accepts auto-generated case id and missing title', () => {
    const rtc: ParsedRefTestCase = {
      caseId: 'Cases!A7',
      caseIdGenerated: true,
      linkedRequirementsRaw: '',
      linkedRequirementKeys: [],
      title: '',
      titleMissing: true,
      action: 'Test action',
      expectedResult: 'Test expected',
      sourceSheet: 'Cases',
      sourceRow: 7,
    };
    expect(rtc.caseIdGenerated).toBe(true);
    expect(rtc.titleMissing).toBe(true);
  });
});

describe('ResolvedLink shape', () => {
  it('accepts a resolved and unresolved link', () => {
    const resolved: ResolvedLink = {
      requirementKey: 'REQ-001',
      refCaseId: 'TC-001',
      resolved: true,
    };
    const unresolved: ResolvedLink = {
      requirementKey: 'REQ-UNKNOWN',
      refCaseId: 'TC-002',
      resolved: false,
    };
    expect(resolved.resolved).toBe(true);
    expect(unresolved.resolved).toBe(false);
  });
});

describe('StyleOnlyCase and NoTestRequirement shapes', () => {
  it('accepts style-only case data', () => {
    const sc: StyleOnlyCase = {
      caseId: 'TC-003',
      title: 'Style example',
      sourceSheet: 'Cases',
      sourceRow: 10,
    };
    expect(sc.title).toBe('Style example');
  });

  it('accepts no-test requirement data', () => {
    const nt: NoTestRequirement = {
      requirementKey: 'REQ-050',
      description: 'No historical test for this',
    };
    expect(nt.requirementKey).toBe('REQ-050');
  });
});

describe('ParsedSummary shape', () => {
  it('accepts a complete parsed summary', () => {
    const summary: ParsedSummary = {
      requirementCount: 100,
      refTestCaseCount: 200,
      validLinkCount: 350,
      noTestRequirementCount: 15,
      styleOnlyCaseCount: 5,
      dataIssueCount: 8,
      dataIssues: [
        { fileType: 'requirement', sheet: 'S1', row: 3, issueType: 'missing_key', message: '...' },
      ],
    };
    expect(summary.validLinkCount).toBe(350);
    expect(summary.dataIssues).toHaveLength(1);
  });
});

describe('LearnedPromptSetMeta shape', () => {
  it('accepts metadata with optional learning instruction', () => {
    const meta: LearnedPromptSetMeta = {
      version: '2026-06-11T143000',
      createdAt: '2026-06-11T14:30:00Z',
      provider: 'ollama',
      model: 'qwen2.5:7b',
      learningInstruction: 'Focus on boundary value tests',
      summary: {
        requirementCount: 50,
        refTestCaseCount: 120,
        validLinkCount: 200,
        noTestRequirementCount: 5,
        styleOnlyCaseCount: 2,
        dataIssueCount: 3,
        dataIssues: [],
      },
    };
    expect(meta.learningInstruction).toBe('Focus on boundary value tests');
  });
});

describe('LearnedPromptSetVersion shape', () => {
  it('accepts a full version with prompt groups', () => {
    const version: LearnedPromptSetVersion = {
      meta: {
        version: '2026-06-11T143000',
        createdAt: '2026-06-11T14:30:00Z',
        provider: 'ollama',
        model: 'qwen2.5:7b',
        summary: {
          requirementCount: 1,
          refTestCaseCount: 1,
          validLinkCount: 1,
          noTestRequirementCount: 0,
          styleOnlyCaseCount: 0,
          dataIssueCount: 0,
          dataIssues: [],
        },
      },
      rationale: '# Learning Rationale\n\n...',
      promptGroups: [
        {
          stage: 'A',
          stageLabel: 'Analyze Test Basis',
          systemPrompt: { filename: 'analyze_test_basis.system.html', content: '<p>sys</p>' },
          userPrompt: { filename: 'analyze_test_basis.user.html', content: '<p>usr</p>' },
        },
      ],
    };
    expect(version.promptGroups).toHaveLength(1);
    expect(version.promptGroups[0].stage).toBe('A');
  });
});

describe('FrameworkValidationResult shape', () => {
  it('accepts valid and invalid results', () => {
    const ok: FrameworkValidationResult = { valid: true, errors: [] };
    const fail: FrameworkValidationResult = {
      valid: false,
      errors: [{ filename: 'generate_case.system.html', message: 'Missing template variable' }],
    };
    expect(ok.valid).toBe(true);
    expect(fail.errors).toHaveLength(1);
  });
});
