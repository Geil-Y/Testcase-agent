import type { CaseIntent } from '../api/types';

const DIM_LABELS: Record<string, string> = {
  normal_behavior: 'Normal Behavior',
  boundary_or_threshold: 'Boundary / Threshold',
  fault_or_protection: 'Fault / Protection',
  state_transition: 'State Transition',
  observability: 'Observability',
};

interface Props {
  intents: CaseIntent[];
  onDelete: (intent: CaseIntent) => void;
  onRegenerate: () => void;
  regenerating: boolean;
}

export default function IntentsPanel({ intents, onDelete, onRegenerate, regenerating }: Props) {
  if (intents.length === 0) {
    return (
      <div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <h2 style={{ fontSize: 16, fontWeight: 600 }}>Case Intents</h2>
          <button className="btn btn-primary" onClick={onRegenerate} disabled={regenerating}>
            {regenerating ? 'Generating...' : 'Regenerate'}
          </button>
        </div>
        <div className="empty-state">
          <h3>No intents planned</h3>
          <p>Click Regenerate to plan case intents with LLM-B.</p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <h2 style={{ fontSize: 16, fontWeight: 600 }}>Case Intents</h2>
          <span className="badge badge-pending">{intents.length} intents</span>
        </div>
        <button className="btn btn-primary" onClick={onRegenerate} disabled={regenerating}>
          {regenerating ? 'Generating...' : 'Regenerate'}
        </button>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {intents.map((intent, idx) => (
          <div
            key={intent.id}
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: 12,
              padding: '10px 14px',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              background: 'var(--bg-surface)',
            }}
          >
            <span style={{ color: 'var(--text-muted)', fontSize: 12, minWidth: 20, paddingTop: 1 }}>#{idx + 1}</span>
            <div style={{ flex: 1 }}>
              <span
                className="badge"
                style={{
                  background: 'var(--bg-hover)',
                  color: 'var(--text-secondary)',
                  fontSize: 10,
                  marginRight: 8,
                }}
              >
                {DIM_LABELS[intent.coverage_dimension] || intent.coverage_dimension}
              </span>
              <span style={{ fontSize: 13 }}>{intent.intent_text}</span>
            </div>
            <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
              <button className="btn btn-xs" onClick={() => onDelete(intent)}>Delete</button>
              <button className="btn btn-xs btn-primary">Accept</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
