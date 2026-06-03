import { useState } from 'react';
import type { SectionItem } from '../api/types';
import { updateItem } from '../api/runs';

interface Props {
  item: SectionItem;
  sectionName: string;
  requirementDescription: string;
  runId: number;
  onClose: () => void;
  onSaved: () => void;
}

function highlightInText(fullText: string, query: string): string {
  if (!query) return escHtml(fullText);
  const idx = fullText.toLowerCase().indexOf(query.toLowerCase());
  if (idx === -1) return escHtml(fullText);
  const before = escHtml(fullText.slice(0, idx));
  const match = escHtml(fullText.slice(idx, idx + query.length));
  const after = escHtml(fullText.slice(idx + query.length));
  return `${before}<mark>${match}</mark>${after}`;
}

function escHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

export default function ItemModal({ item, sectionName, requirementDescription, runId, onClose, onSaved }: Props) {
  const [status, setStatus] = useState(item.status);
  const [content, setContent] = useState(item.content);
  const [need, setNeed] = useState(item.need);
  const [saving, setSaving] = useState(false);

  const srcText = item.source_text?.replace(/^"|"$/g, '') || '';
  const highlighted = highlightInText(requirementDescription, srcText);

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateItem(runId, sectionName, item.item_id, { status, content, need });
      onSaved();
      onClose();
    } catch (e) {
      alert('Save failed: ' + String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{item.item_id} · {sectionName}</h3>
          <button className="modal-close" onClick={onClose}>&times;</button>
        </div>
        <div className="modal-body">
          <div className="mf">
            <label>Requirement</label>
            <div
              className="src-block"
              style={{ borderLeftColor: 'var(--text-muted)', fontStyle: 'normal', fontSize: 13, lineHeight: 1.6 }}
              dangerouslySetInnerHTML={{ __html: highlighted }}
            />
          </div>
          <div className="mf">
            <label>Status</label>
            <select value={status} onChange={(e) => setStatus(e.target.value as SectionItem['status'])}>
              <option value="known">known — explicitly in requirement</option>
              <option value="needs_review">needs_review — missing from requirement</option>
            </select>
          </div>
          <div className="mf">
            <label>Content</label>
            <textarea value={content} onChange={(e) => setContent(e.target.value)} placeholder="Extracted value..." rows={3} />
          </div>
          <div className="mf">
            <label>Missing Need</label>
            <textarea value={need} onChange={(e) => setNeed(e.target.value)} placeholder="Describe what information is missing..." rows={2} style={{ color: status === 'needs_review' ? 'var(--warning)' : undefined }} />
          </div>
        </div>
        <div className="modal-footer">
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn" onClick={onClose}>Flag</button>
          <button className="btn btn-primary" onClick={handleSave} disabled={saving}>{saving ? 'Saving...' : 'Accept'}</button>
        </div>
      </div>
    </div>
  );
}
