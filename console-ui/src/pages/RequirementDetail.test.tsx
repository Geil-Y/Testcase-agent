import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import RequirementDetail from './RequirementDetail';

const mockReq = {
  requirement: { id: 1, requirement_key: 'REQ-001', description: 'BMS OV Detection', function_name: 'OVP', requirement_type: 'req', supplementary_info: '', source_row: 1, imported_at: '' },
  runs: [{ id: 1, status: 'cases_ready', review_llm_a: 0, review_llm_b: 0, review_llm_c: 0, created_at: '2026-01-01' }],
};

let mockData = mockReq;

vi.mock('../api/requirements', () => ({
  getRequirement: vi.fn().mockImplementation(() => Promise.resolve(mockData)),
}));

vi.mock('../api/runs', () => ({
  createRun: vi.fn().mockResolvedValue({ run: { id: 2 } }),
}));

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/requirements/1']}>
      <Routes>
        <Route path="/requirements/:id" element={<RequirementDetail />} />
        <Route path="/runs/:runId" element={<div>Workspace</div>} />
      </Routes>
    </MemoryRouter>
  );
}

describe('RequirementDetail', () => {
  beforeEach(() => { mockData = mockReq; });

  it('renders requirement key and description', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('REQ-001')).toBeDefined();
      expect(screen.getByText('BMS OV Detection')).toBeDefined();
    });
  });

  it('shows review config on Start New Run click', async () => {
    renderPage();
    await waitFor(() => screen.getByText('Start New Run'));
    fireEvent.click(screen.getByText('Start New Run'));
    expect(screen.getByText('LLM-A requires review (extraction)')).toBeDefined();
    expect(screen.getByText('LLM-B requires review (case intents)')).toBeDefined();
    expect(screen.getByText('LLM-C requires review (test cases)')).toBeDefined();
  });

  it('creates run with review options', async () => {
    const { createRun } = await import('../api/runs');
    renderPage();
    await waitFor(() => screen.getByText('Start New Run'));
    fireEvent.click(screen.getByText('Start New Run'));
    fireEvent.click(screen.getByLabelText('LLM-A requires review (extraction)'));
    fireEvent.click(screen.getByText('Create Run'));
    await waitFor(() => expect(createRun).toHaveBeenCalledWith(1, ['a']));
  });

  it('shows existing runs', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('Previous Runs')).toBeDefined());
  });
});
