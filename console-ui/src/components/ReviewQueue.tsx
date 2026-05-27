import type { ReviewItem } from '../api/types'

interface Props {
  items: ReviewItem[]
  selectedId: string | null
  onSelect: (id: string) => void
  validationErrors: Map<string, string[]>
  decisionFilter: string
  routingFilter: string
  search: string
  onDecisionFilter: (v: string) => void
  onRoutingFilter: (v: string) => void
  onSearch: (v: string) => void
}

const DECISION_LABELS: Record<string, string> = {
  '': 'All',
  pending: 'Pending',
  approve: 'Approved',
  clarify: 'Clarified',
  mark_needs_review: 'Needs Review',
  block: 'Blocked',
  edit_content: 'Edited',
}

const ROUTING_COLORS = ['', 'red', 'orange', 'blue', 'green']
const ROUTING_LABELS: Record<string, string> = {
  '': 'All',
  red: 'Red',
  orange: 'Orange',
  blue: 'Blue',
  green: 'Green',
}

export default function ReviewQueue({
  items, selectedId, onSelect, validationErrors,
  decisionFilter, routingFilter, search,
  onDecisionFilter, onRoutingFilter, onSearch,
}: Props) {
  return (
    <div className="review-queue">
      <div className="queue-filters">
        <input
          type="search"
          placeholder="Search..."
          value={search}
          onChange={(e) => onSearch(e.target.value)}
          className="queue-search"
        />
        <select value={decisionFilter} onChange={(e) => onDecisionFilter(e.target.value)}>
          {Object.entries(DECISION_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
        <select value={routingFilter} onChange={(e) => onRoutingFilter(e.target.value)}>
          {ROUTING_COLORS.map((c) => (
            <option key={c} value={c}>{ROUTING_LABELS[c]}</option>
          ))}
        </select>
      </div>

      <div className="queue-list">
        {items.length === 0 && <p className="text-muted">No items match filters.</p>}
        {items.map((item) => {
          const hasErrors = validationErrors.has(item.item_id)
          const decision = item.decision || 'pending'
          return (
            <button
              key={item.item_id}
              className={`queue-row ${item.item_id === selectedId ? 'selected' : ''} ${hasErrors ? 'has-error' : ''}`}
              onClick={() => onSelect(item.item_id)}
            >
              <span className={`routing-dot routing-${item.routing_color || 'blue'}`} />
              <span className="queue-item-id">{item.item_id}</span>
              <span className={`queue-decision dec-${decision}`}>
                {DECISION_LABELS[decision] || decision}
              </span>
              {item.recommended_decision && item.recommended_decision !== decision && (
                <span className="queue-recommended text-muted">
                  rec: {DECISION_LABELS[item.recommended_decision] || item.recommended_decision}
                </span>
              )}
              {item.ambiguity_type && (
                <span className="queue-type text-muted">{item.ambiguity_type}</span>
              )}
              {hasErrors && <span className="queue-error-icon" title="Has validation errors">!</span>}
            </button>
          )
        })}
      </div>
    </div>
  )
}
