import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import EvaluationSummary from './EvaluationSummary';
import type { EvaluationSummary as EvalSum } from '../api/types';

const mock: EvalSum = {
  total_cases: 4, passed: 3, failed: 1, pass_rate: 0.75,
  cases: [
    { case_id: 1, title: 'C1', passed: true, failed_items: [], warning_items: [] },
    { case_id: 2, title: 'C2', passed: false, failed_items: ['3.2.1'], warning_items: ['3.3.3'] },
  ],
};

describe('EvaluationSummary', () => {
  it('renders pass rate and counts', () => {
    render(<EvaluationSummary evaluation={mock} cases={[]} />);
    expect(screen.getByText('75%')).toBeDefined();
    expect(screen.getByText('4')).toBeDefined();
    expect(screen.getByText('3')).toBeDefined();
    expect(screen.getByText('1')).toBeDefined();
  });
});
