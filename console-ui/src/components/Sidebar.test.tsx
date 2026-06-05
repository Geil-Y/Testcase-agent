import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import Sidebar from './Sidebar';
import type { Requirement, Section, SectionItem } from '../api/types';

const mockReq: Requirement = {
  id: 1, requirement_key: 'REQ-001', description: 'BMS Cell Overvoltage Detection',
  function_name: 'OVP_Detection', requirement_type: 'requirement',
  supplementary_info: '', source_row: 1, imported_at: '2026-01-01',
};

const mockSections: Section[] = [
  {
    section_name: 'signals',
    items: [
      { id: 1, item_id: 'sig-1', status: 'known', content: 'BMS_CellOV_Detect', need: '', source_text: '', sort_order: 0 },
      { id: 2, item_id: 'sig-2', status: 'needs_review', content: '', need: 'Cell voltage missing', source_text: '', sort_order: 1 },
    ],
  },
  {
    section_name: 'thresholds',
    items: [{ id: 3, item_id: 'thr-1', status: 'known', content: 'r_CellOV_Threshold', need: '', source_text: '', sort_order: 0 }],
  },
];

function renderSb(props: Partial<{
  onItemClick: (item: SectionItem, sectionName: string) => void;
  onAddItem: (sectionName: string) => void;
  onDeleteItem: (item: SectionItem, sectionName: string) => void;
  accepted: boolean;
}> = {}) {
  return render(
    <Sidebar
      requirement={mockReq}
      sections={mockSections}
      onItemClick={props.onItemClick ?? vi.fn()}
      onAddItem={props.onAddItem ?? vi.fn()}
      onDeleteItem={props.onDeleteItem ?? vi.fn()}
      accepted={props.accepted ?? false}
      runId={1}
      onRegenerated={vi.fn()}
    />
  );
}

describe('Sidebar', () => {
  it('renders requirement description', () => {
    renderSb();
    expect(screen.getByText('BMS Cell Overvoltage Detection')).toBeDefined();
  });

  it('renders section headers with item counts', () => {
    renderSb();
    expect(screen.getByText('signals')).toBeDefined();
    expect(screen.getByText('2 items')).toBeDefined();
    expect(screen.getByText('1 items')).toBeDefined();
  });

  it('collapses and expands sections', () => {
    renderSb();
    expect(screen.getByText('sig-1')).toBeDefined();
    fireEvent.click(screen.getByText('signals'));
    expect(screen.queryByText('sig-1')).toBeNull();
    fireEvent.click(screen.getByText('signals'));
    expect(screen.getByText('sig-1')).toBeDefined();
  });

  it('calls onItemClick with item and section name', () => {
    const onClick = vi.fn();
    renderSb({ onItemClick: onClick });
    fireEvent.click(screen.getByText('sig-1'));
    expect(onClick).toHaveBeenCalledWith(mockSections[0].items[0], 'signals');
  });

  it('shows known and needs_review badges', () => {
    renderSb();
    expect(screen.getAllByText('known').length).toBe(2);
    expect(screen.getByText('needs review')).toBeDefined();
  });

  it('renders + buttons in section headers', () => {
    renderSb();
    const btns = screen.getAllByTitle('Add item');
    expect(btns.length).toBe(2);
  });

  it('calls onAddItem when + is clicked', () => {
    const onAdd = vi.fn();
    renderSb({ onAddItem: onAdd });
    const btns = screen.getAllByTitle('Add item');
    fireEvent.click(btns[0]);
    expect(onAdd).toHaveBeenCalledWith('signals');
  });

  it('renders × buttons on items', () => {
    renderSb();
    const btns = screen.getAllByTitle('Delete item');
    expect(btns.length).toBe(3);
  });

  it('calls onDeleteItem when × is clicked', () => {
    const onDel = vi.fn();
    renderSb({ onDeleteItem: onDel });
    const btns = screen.getAllByTitle('Delete item');
    fireEvent.click(btns[0]);
    expect(onDel).toHaveBeenCalledWith(mockSections[0].items[0], 'signals');
  });
});
