import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import CaseGroup from './CaseGroup';
import type { TestCase, CaseIntent } from '../api/types';

const mockCase: TestCase = {
  id: 1, title: 'OV detection when voltage exceeds threshold',
  objective: 'Verify OV detection', precondition: 'BMS initialized',
  postcondition: 'Normal state', raw_html: '', sort_order: 0, intent_id: 1,
  steps: [
    { id: 1, step_order: 1, action: 'Set cell voltage above threshold', expected: 'Voltage above threshold' },
    { id: 2, step_order: 2, action: 'Wait [NEEDS REVIEW]', expected: 'BMS_CellOV_Detect := 1' },
  ],
  evaluation_items: [],
};

const mockIntent: CaseIntent = {
  id: 1, intent_id: 'intent-1', coverage_dimension: 'normal_behavior',
  intent_text: 'Verify OV detection when voltage exceeds threshold.', sort_order: 0,
};

describe('CaseGroup', () => {
  it('renders case title and intent', () => {
    render(<CaseGroup case_={mockCase} intent={mockIntent} index={0} dimLabel="Normal Behavior" />);
    expect(screen.getByText('OV detection when voltage exceeds threshold')).toBeDefined();
    expect(screen.getByText('#1')).toBeDefined();
    expect(screen.getByText('Normal Behavior')).toBeDefined();
  });

  it('renders steps with [NEEDS REVIEW] highlighted', () => {
    render(<CaseGroup case_={mockCase} intent={mockIntent} index={0} dimLabel="Normal Behavior" />);
    const nr = screen.getByText('[NEEDS REVIEW]');
    expect(nr.className).toContain('needs-review');
  });

  it('shows pass badge when evaluation passes', () => {
    const c = { ...mockCase, evaluation_items: [{ id: 1, item_id: '1.1.1', result: 'pass' as const, detail: '' }] };
    render(<CaseGroup case_={c} intent={mockIntent} index={0} dimLabel="NB" />);
    expect(screen.getByText('✓ Passed')).toBeDefined();
  });

  it('shows fail badge with item IDs when evaluation fails', () => {
    const c = { ...mockCase, evaluation_items: [
      { id: 1, item_id: '3.2.1', result: 'fail' as const, detail: '' },
      { id: 2, item_id: '3.2.2', result: 'warn' as const, detail: '' },
    ]};
    render(<CaseGroup case_={c} intent={mockIntent} index={0} dimLabel="NB" />);
    expect(screen.getByText('✗ Failed')).toBeDefined();
    expect(screen.getByText(/3.2.1/)).toBeDefined();
  });

  it('renders without intent', () => {
    render(<CaseGroup case_={mockCase} intent={null} index={0} dimLabel="" />);
    expect(screen.getByText('OV detection when voltage exceeds threshold')).toBeDefined();
  });
});
