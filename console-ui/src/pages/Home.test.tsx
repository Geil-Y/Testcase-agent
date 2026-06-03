import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import Home from './Home';

const mockItems = [
  { id: 1, requirement_key: 'REQ-001', description: 'Cell overvoltage', function_name: 'OVP', requirement_type: 'req', supplementary_info: '', source_row: 1, imported_at: '' },
  { id: 2, requirement_key: 'REQ-002', description: 'Cell undervoltage', function_name: 'UVP', requirement_type: 'req', supplementary_info: '', source_row: 2, imported_at: '' },
];

let mockData = { items: mockItems, total: 2 };

vi.mock('../api/requirements', () => ({
  listRequirements: vi.fn().mockImplementation(() => Promise.resolve(mockData)),
  importRequirements: vi.fn().mockResolvedValue({ imported: 5, total_rows: 10 }),
}));

function renderHome() {
  return render(<MemoryRouter><Home /></MemoryRouter>);
}

describe('Home', () => {
  beforeEach(() => { mockData = { items: mockItems, total: 2 }; });

  it('renders search input', async () => {
    renderHome();
    await waitFor(() => expect(screen.getByPlaceholderText('Search requirements... (/)')).toBeDefined());
  });

  it('renders requirement rows after load', async () => {
    renderHome();
    await waitFor(() => {
      expect(screen.getByText('REQ-001')).toBeDefined();
      expect(screen.getByText('REQ-002')).toBeDefined();
    });
  });

  it('shows total count', async () => {
    renderHome();
    await waitFor(() => expect(screen.getByText('2 of 2')).toBeDefined());
  });

  it('shows empty state', async () => {
    mockData = { items: [], total: 0 };
    renderHome();
    await waitFor(() =>
      expect(screen.getByText('No requirements found. Import an Excel file to get started.')).toBeDefined()
    );
  });

  it('renders filter chips', async () => {
    renderHome();
    await waitFor(() => {
      expect(screen.getByText('All')).toBeDefined();
      expect(screen.getByText('New')).toBeDefined();
      expect(screen.getByText('Pending')).toBeDefined();
      expect(screen.getByText('Reviewed')).toBeDefined();
    });
  });

  it('/ focuses search input', async () => {
    renderHome();
    await waitFor(() => screen.getByPlaceholderText('Search requirements... (/)'));
    const input = screen.getByPlaceholderText('Search requirements... (/)');
    input.blur();
    fireEvent.keyDown(document.body, { key: '/' });
    await waitFor(() => expect(document.activeElement).toBe(input));
  });
});
