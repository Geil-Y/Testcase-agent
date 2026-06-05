import { useState } from 'react';
import type { Requirement, Section, SectionItem } from '../api/types';
import { regenerateItem } from '../api/runs';

interface Props {
  requirement: Requirement;
  sections: Section[];
  onItemClick: (item: SectionItem, sectionName: string) => void;
  onAddItem: (sectionName: string) => void;
  onDeleteItem: (item: SectionItem, sectionName: string) => void;
  accepted: boolean;
  runId: number;
  onRegenerated: () => void;
}

export default function Sidebar({ requirement, sections, onItemClick, onAddItem, onDeleteItem, accepted, runId, onRegenerated }: Props) {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [regenItem, setRegenItem] = useState<{ item: SectionItem; sectionName: string } | null>(null);
  const [regenComment, setRegenComment] = useState('');
  const [regenning, setRegenning] = useState(false);

  const toggle = (name: string) => setCollapsed((p) => ({ ...p, [name]: !p[name] }));

  const handleRegen = async () => {
    if (!regenItem || !regenComment.trim()) return;
    setRegenning(true);
    try {
      await regenerateItem(runId, regenItem.sectionName, regenItem.item.item_id, regenComment.trim());
      setRegenItem(null);
      setRegenComment('');
      onRegenerated();
    } catch (e) {
      alert('Regenerate failed: ' + String(e));
    } finally {
      setRegenning(false);
    }
  };

  return (
    <div className="sidebar">
      <div className="sidebar-scroll">
        <div className="sb-req">
          <h4>Requirement</h4>
          <p>{requirement.description}</p>
        </div>

        {sections.map((sec) => (
          <div key={sec.section_name} className="sb-section">
            <div className="sb-section-header" onClick={() => toggle(sec.section_name)}>
              <span>{sec.section_name}</span>
              <span className="text-muted" style={{ fontSize: 11 }}>{sec.items.length} items</span>
              {!accepted && (
                <button className="btn btn-xs" style={{ marginLeft: 'auto' }} onClick={(e) => { e.stopPropagation(); onAddItem(sec.section_name); }} title="Add item">+</button>
              )}
            </div>
            {!collapsed[sec.section_name] && (
              <div className="sb-section-body">
                {sec.items.map((item) => (
                  <div
                    key={item.id}
                    className={`sb-item ${selectedId === String(item.id) ? 'selected' : ''}`}
                    onClick={() => { setSelectedId(String(item.id)); onItemClick(item, sec.section_name); }}
                  >
                    <div className="sb-item-header">
                      <span className="sb-item-id">
                        {accepted && <span title="Locked (accepted)">🔒 </span>}
                        {item.item_id}
                      </span>
                      <span className={`badge ${item.status === 'known' ? 'badge-known' : 'badge-needs'}`}>
                        {item.status === 'known' ? 'known' : 'needs review'}
                      </span>
                      {!accepted && (
                        <>
                          <button className="btn btn-xs sb-item-del" onClick={(e) => { e.stopPropagation(); onDeleteItem(item, sec.section_name); }} title="Delete item">&times;</button>
                          <button className="btn btn-xs" style={{ marginLeft: 4, background: 'var(--accent)', color: '#fff' }} onClick={(e) => { e.stopPropagation(); setRegenItem({ item, sectionName: sec.section_name }); setRegenComment(''); }} title="Regenerate">R</button>
                        </>
                      )}
                    </div>
                    {item.content && <div className="sb-item-content">{item.content}</div>}
                    {item.need && <div className="sb-item-need">{item.need}</div>}
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}

        {regenItem && (
          <div className="regen-panel">
            <h4>Regenerate: {regenItem.item.item_id}</h4>
            <textarea
              value={regenComment}
              onChange={(e) => setRegenComment(e.target.value)}
              placeholder="Enter review comment (required)..."
              rows={3}
            />
            <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
              <button className="btn btn-primary" onClick={handleRegen} disabled={regenning || !regenComment.trim()}>
                {regenning ? 'Regenerating...' : 'Regenerate'}
              </button>
              <button className="btn" onClick={() => setRegenItem(null)}>Cancel</button>
            </div>
          </div>
        )}

        <div className="sb-blocker">
          <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.03em', marginBottom: 4 }}>
            Blocking Gaps
          </div>
          <textarea placeholder="None identified." defaultValue="" />
        </div>
      </div>
    </div>
  );
}
