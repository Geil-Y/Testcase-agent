import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import PromptLearning from './PromptLearning';

const { inspectWorkbooks: mockInspect } = vi.hoisted(() => ({
  inspectWorkbooks: vi.fn().mockResolvedValue({
    requirement: {
      filename: 'req.xlsx',
      sheets: [
        { name: 'Requirements', columns: ['Req ID', 'Description', 'Func', 'Type'] },
      ],
    },
    referenceTestCase: {
      filename: 'case.xlsx',
      sheets: [
        { name: 'Cases', columns: ['Case ID', 'Req Link', 'Title', 'Action', 'Expected', 'Obj'] },
      ],
    },
  }),
}));

vi.mock('../api/pl-api', () => ({
  inspectWorkbooks: mockInspect,
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <PromptLearning />
    </MemoryRouter>
  );
}

// Helper: simulate choosing files and inspecting
async function inspectFiles() {
  // Simulate choosing files via the hidden inputs
  const fileInputs = document.querySelectorAll('input[type="file"]');
  expect(fileInputs).toHaveLength(2);

  // Create mock File objects
  const reqFile = new File(['dummy'], 'req.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
  const caseFile = new File(['dummy'], 'case.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });

  fireEvent.change(fileInputs[0], { target: { files: [reqFile] } });
  fireEvent.change(fileInputs[1], { target: { files: [caseFile] } });

  // Click Inspect Workbooks
  const inspectBtn = screen.getByText('Inspect Workbooks');
  expect((inspectBtn as HTMLButtonElement).disabled).toBe(false);
  fireEvent.click(inspectBtn);

  await waitFor(() => {
    expect(screen.getByText('2. Select Sheets')).toBeDefined();
  });
}

describe('PromptLearning', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('renders the page header', () => {
    renderPage();
    expect(screen.getByRole('heading', { name: 'Prompt Learning', level: 1 })).toBeDefined();
  });

  it('renders upload section with two Choose File buttons', () => {
    renderPage();
    expect(screen.getAllByText('Choose File')).toHaveLength(2);
  });

  it('Inspect button is disabled until files are selected', () => {
    renderPage();
    const btn = screen.getByText('Inspect Workbooks');
    expect((btn as HTMLButtonElement).disabled).toBe(true);
  });

  it('shows sheet selection and column mapping after inspection', async () => {
    renderPage();
    await inspectFiles();

    // Sheet selection UI visible
    expect(screen.getByText('Requirement Sheet')).toBeDefined();
    expect(screen.getByText('Reference Test Case Sheets')).toBeDefined();

    // Column mapping UI visible
    expect(screen.getByText('3. Map Columns')).toBeDefined();
    expect(screen.getByText(/Requirement Key/)).toBeDefined();
    expect(screen.getByText(/Linked Requirements/)).toBeDefined();
  });

  it('shows error message when inspection fails', async () => {
    mockInspect.mockRejectedValueOnce(new Error('Cannot read workbook'));

    renderPage();

    // Choose files
    const fileInputs = document.querySelectorAll('input[type="file"]');
    fireEvent.change(fileInputs[0], { target: { files: [new File([''], 'r.xlsx')] } });
    fireEvent.change(fileInputs[1], { target: { files: [new File([''], 'c.xlsx')] } });

    fireEvent.click(screen.getByText('Inspect Workbooks'));

    await waitFor(() => {
      expect(screen.getByText('Cannot read workbook')).toBeDefined();
    });
  });

  it('toggles case sheet checkboxes', async () => {
    renderPage();
    await inspectFiles();

    const checkboxes = document.querySelectorAll('.pl-checkbox input[type="checkbox"]') as NodeListOf<HTMLInputElement>;
    expect(checkboxes).toHaveLength(1);
    expect(checkboxes[0].checked).toBe(true);

    fireEvent.click(checkboxes[0]);
    expect(checkboxes[0].checked).toBe(false);

    fireEvent.click(checkboxes[0]);
    expect(checkboxes[0].checked).toBe(true);
  });
});

describe('PromptLearning localStorage persistence', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('saves mapping to localStorage after inspection', async () => {
    renderPage();
    await inspectFiles();

    // Select a column mapping value
    const selects = document.querySelectorAll('.pl-mapping-grid select');
    expect(selects.length).toBeGreaterThan(0);

    // Change a required column select
    fireEvent.change(selects[0], { target: { value: 'Req ID' } });

    await waitFor(() => {
      const stored = localStorage.getItem('pl_column_mapping');
      expect(stored).not.toBeNull();
      const parsed = JSON.parse(stored!);
      expect(parsed.reqCols.requirementKey).toBe('Req ID');
    });
  });

  it('restores mapping on next inspection', async () => {
    // Pre-populate localStorage
    localStorage.setItem('pl_column_mapping', JSON.stringify({
      reqSheet: 'Requirements',
      caseSheets: ['Cases'],
      reqCols: { requirementKey: 'Req ID', description: 'Description' },
      caseCols: { linkedRequirements: 'Req Link', title: 'Title', action: 'Action', expectedResult: 'Expected' },
    }));

    renderPage();
    await inspectFiles();

    // The column selects should show the restored values after effect runs
    await waitFor(() => {
      const selects = document.querySelectorAll('.pl-mapping-grid select');
      const reqKeySelect = selects[0] as HTMLSelectElement;
      expect(reqKeySelect.value).toBe('Req ID');
    });
  });

  it('handles stale mapping — clears columns not in current workbook', async () => {
    // Pre-populate with a column that doesn't exist in the inspection result
    localStorage.setItem('pl_column_mapping', JSON.stringify({
      reqSheet: 'Requirements',
      caseSheets: ['Cases'],
      reqCols: { requirementKey: 'Old_Col', description: 'Description' },
      caseCols: { linkedRequirements: 'Req Link', title: 'Title', action: 'Action', expectedResult: 'Expected' },
    }));

    renderPage();
    await inspectFiles();

    // 'Old_Col' is not in the available columns — should be cleared
    const selects = document.querySelectorAll('.pl-mapping-grid select');
    const reqKeySelect = selects[0] as HTMLSelectElement;
    expect(reqKeySelect.value).toBe(''); // cleared because "Old_Col" not present
  });
});
