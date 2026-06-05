import { useState } from 'react';
import type { Requirement, Section, SectionItem } from '../api/types';

interface Props {
  requirement: Requirement;
  sections: Section[];
  onItemClick: (item: SectionItem, sectionName: string) => void;
  onAddItem: (sectionName: string) => void;
  onDeleteItem: (item: SectionItem, sectionName: string) => void;
}

export default function Sidebar({ requirement, sections, onItemClick, onAddItem, onDeleteItem }: Props) {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const toggle = (name: string) => setCollapsed((p) => ({ ...p, [name]: !p[name] }));

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
              <button className="btn btn-xs" style={{ marginLeft: 'auto' }} onClick={(e) => { e.stopPropagation(); onAddItem(sec.section_name); }} title="Add item">+</button>
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
                      <span className="sb-item-id">{item.item_id}</span>
                      <span className={`badge ${item.status === 'known' ? 'badge-known' : 'badge-needs'}`}>
                        {item.status === 'known' ? 'known' : 'needs review'}
                      </span>
                      <button className="btn btn-xs sb-item-del" onClick={(e) => { e.stopPropagation(); onDeleteItem(item, sec.section_name); }} title="Delete item">&times;</button>
                    </div>
                    {item.content && <div className="sb-item-content">{item.content}</div>}
                    {item.need && <div className="sb-item-need">{item.need}</div>}
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}

      </div>
    </div>
  );
}
