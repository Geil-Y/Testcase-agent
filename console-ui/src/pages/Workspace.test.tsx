import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';
import Workspace from './Workspace';
import type { RunDetail } from '../api/types';

const base: RunDetail = {
  run: { id: 1, requirement_id: 1, status: 'extraction_ready', review_llm_a: 0, review_llm_b: 0, review_llm_c: 0, error: null, created_at: '', updated_at: '' },
  requirement: { id: 1, requirement_key: 'REQ-001', description: 'BMS OV Detection', function_name: 'OVP', requirement_type: 'req', supplementary_info: '', source_row: 1, imported_at: '' },
  sections: [
    { section_name: 'signals', items: [{ id: 1, item_id: 'sig-1', status: 'known', content: 'BMS_CellOV_Detect', need: '', source_text: '', sort_order: 0 }] },
    { section_name: 'thresholds', items: [] }, { section_name: 'timing', items: [] }, { section_name: 'states', items: [] }, { section_name: 'observations', items: [] },
  ],
  intents: [], cases: [], evaluation: null,
};

const withCases: RunDetail = {
  ...base, run: { ...base.run, status: 'cases_ready' },
  intents: [{ id: 1, intent_id: 'intent-1', coverage_dimension: 'normal_behavior', intent_text: 'Verify OV', sort_order: 0 }],
  cases: [{ id: 1, title: 'OV test', objective: 'Verify', precondition: 'Init', postcondition: 'Done', raw_html: '', sort_order: 0, intent_id: 1, steps: [{ id: 1, step_order: 1, action: 'Set voltage', expected: 'Triggers' }], evaluation_items: [] }],
};

let mockData = base;

vi.mock('../api/runs', () => ({
  getRun: vi.fn().mockImplementation(() => Promise.resolve(mockData)),
  advanceRun: vi.fn().mockResolvedValue({}),
  evaluateRun: vi.fn().mockResolvedValue({ summary: { total_cases: 1, passed: 1, failed: 0, pass_rate: 1 }, cases: [] }),
  addItem: vi.fn().mockResolvedValue({}),
  deleteItem: vi.fn().mockResolvedValue(undefined),
  updateCase: vi.fn().mockResolvedValue({}),
  deleteIntent: vi.fn().mockResolvedValue(undefined),
  regenerateIntents: vi.fn().mockResolvedValue({}),
}));

function renderWs(data: RunDetail) {
  mockData = data;
  return render(
    <MemoryRouter initialEntries={['/runs/1']}>
      <Routes><Route path="/runs/:runId" element={<Workspace />} /></Routes>
    </MemoryRouter>
  );
}

describe('Workspace', () => {
  it('shows Plan Case Intents when extraction_ready', async () => {
    renderWs(base);
    await waitFor(() => expect(screen.getByText('Plan Case Intents')).toBeDefined());
  });

  it('shows Generate Cases when intents_ready', async () => {
    renderWs({ ...base, run: { ...base.run, status: 'intents_ready' } });
    await waitFor(() => expect(screen.getByText('Generate Cases')).toBeDefined());
  });

  it('shows Run Evaluation when cases_ready', async () => {
    renderWs(withCases);
    await waitFor(() => expect(screen.getByText('Run Evaluation')).toBeDefined());
  });

  it('shows empty state when extraction_ready', async () => {
    renderWs(base);
    await waitFor(() => expect(screen.getByText('Intents not yet planned')).toBeDefined());
  });

  it('calls advance on button click', async () => {
    const { advanceRun } = await import('../api/runs');
    renderWs(base);
    await waitFor(() => screen.getByText('Plan Case Intents'));
    fireEvent.click(screen.getByText('Plan Case Intents'));
    await waitFor(() => expect(advanceRun).toHaveBeenCalledWith(1));
  });

  it('shows loading state during advance', async () => {
    renderWs(base);
    await waitFor(() => screen.getByText('Plan Case Intents'));
    fireEvent.click(screen.getByText('Plan Case Intents'));
    expect(screen.getByText('Planning...')).toBeDefined();
  });
});
