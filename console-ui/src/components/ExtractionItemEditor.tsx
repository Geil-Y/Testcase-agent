import type { SectionItem } from '../api/types'

interface Props {
  item: SectionItem | null
  onEdit: (changes: Partial<SectionItem>) => void
}

const SECTION_ITEM_FIELDS: (keyof SectionItem)[] = ['item_id', 'status', 'content', 'need', 'source_text']

export default function ExtractionItemEditor({ item, onEdit }: Props) {
  if (!item) {
    return <div className="card review-detail"><p className="text-muted">Select an item to edit.</p></div>
  }

  return (
    <div className="card review-detail">
      <h3>{item.item_id}</h3>

      <div className="detail-grid">
        {SECTION_ITEM_FIELDS.map((field) => (
          <div key={field} className="detail-field">
            <label>{field.replace(/_/g, ' ')}</label>
            {field === 'status' ? (
              <select
                value={item.status || 'known'}
                onChange={(e) => onEdit({ status: e.target.value as SectionItem['status'] })}
              >
                <option value="known">known</option>
                <option value="unknown">unknown</option>
                <option value="assumed">assumed</option>
              </select>
            ) : field === 'content' || field === 'need' ? (
              <textarea
                value={item[field] || ''}
                onChange={(e) => onEdit({ [field]: e.target.value })}
                rows={3}
              />
            ) : (
              <input
                type="text"
                value={String(item[field] || '')}
                onChange={(e) => onEdit({ [field]: e.target.value })}
              />
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
