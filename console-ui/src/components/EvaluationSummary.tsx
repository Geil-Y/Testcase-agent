import type { EvaluationSummary as EvalSummary, TestCase } from '../api/types';

interface Props {
  evaluation: EvalSummary;
  cases: TestCase[];
}

export default function EvaluationSummary({ evaluation }: Props) {
  const { total_cases, passed, failed, pass_rate } = evaluation;
  const color = pass_rate >= 0.9 ? 'var(--success)' : pass_rate >= 0.7 ? 'var(--warning)' : 'var(--danger)';

  return (
    <div className="eval-summary">
      <div className="eval-card">
        <div className="value" style={{ color }}>{(pass_rate * 100).toFixed(0)}%</div>
        <div className="label">Pass Rate</div>
      </div>
      <div className="eval-card">
        <div className="value">{total_cases}</div>
        <div className="label">Total Cases</div>
      </div>
      <div className="eval-card">
        <div className="value" style={{ color: 'var(--success)' }}>{passed}</div>
        <div className="label">Passed</div>
      </div>
      <div className="eval-card">
        <div className="value" style={{ color: 'var(--danger)' }}>{failed}</div>
        <div className="label">Failed</div>
      </div>
    </div>
  );
}
