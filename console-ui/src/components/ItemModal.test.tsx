import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import ItemModal from './ItemModal';
import type { SectionItem } from '../api/types';

const mockItem: SectionItem = {
  id: 1, item_id: 'sig-1', status: 'known', content: 'BMS_CellOV_Detect',
  need: '', source_text: 'Cell overvoltage', sort_order: 0,
};

vi.mock('../api/runs', () => ({ updateItem: vi.fn().mockResolvedValue({}) }));

describe('ItemModal', () => {
  it('renders item header', () => {
    render(<ItemModal item={mockItem} sectionName="signals"
      requirementDescription="BMS Cell Overvoltage Detection" runId={1}
      onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.getByText(/sig-1 · signals/)).toBeDefined();
  });

  it('renders status dropdown', () => {
    render(<ItemModal item={mockItem} sectionName="signals"
      requirementDescription="desc" runId={1} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect((screen.getByRole('combobox') as HTMLSelectElement).value).toBe('known');
  });

  it('renders editable textareas', () => {
    render(<ItemModal item={mockItem} sectionName="signals"
      requirementDescription="desc" runId={1} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.getByPlaceholderText('Extracted value...')).toBeDefined();
    expect(screen.getByPlaceholderText('Describe what information is missing...')).toBeDefined();
  });

  it('closes on × button', () => {
    const onClose = vi.fn();
    render(<ItemModal item={mockItem} sectionName="signals" requirementDescription="desc"
      runId={1} onClose={onClose} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: '×' }));
    expect(onClose).toHaveBeenCalled();
  });

  it('closes on Cancel', () => {
    const onClose = vi.fn();
    render(<ItemModal item={mockItem} sectionName="signals" requirementDescription="desc"
      runId={1} onClose={onClose} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByText('Cancel'));
    expect(onClose).toHaveBeenCalled();
  });

  it('highlights source text', () => {
    render(<ItemModal item={mockItem} sectionName="signals"
      requirementDescription="BMS Cell Overvoltage Detection" runId={1}
      onClose={vi.fn()} onSaved={vi.fn()} />);
    const mark = document.querySelector('mark');
    expect(mark).toBeTruthy();
    expect(mark?.textContent?.toLowerCase()).toBe('cell overvoltage');
  });

  it('no highlight when source empty', () => {
    render(<ItemModal item={{ ...mockItem, source_text: '' }} sectionName="signals"
      requirementDescription="desc" runId={1} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(document.querySelector('mark')).toBeNull();
  });

  it('saves and closes on Accept', async () => {
    const onClose = vi.fn();
    const onSaved = vi.fn();
    const { updateItem } = await import('../api/runs');
    render(<ItemModal item={mockItem} sectionName="signals" requirementDescription="desc"
      runId={1} onClose={onClose} onSaved={onSaved} />);
    fireEvent.click(screen.getByText('Accept'));
    await waitFor(() => {
      expect(updateItem).toHaveBeenCalledWith(1, 'signals', 'sig-1',
        { status: 'known', content: 'BMS_CellOV_Detect', need: '' });
      expect(onSaved).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });
});
