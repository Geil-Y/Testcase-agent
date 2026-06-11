import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';
import { AppShell } from './App';

vi.mock('./api/requirements', () => ({
  listRequirements: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  importRequirements: vi.fn(),
}));

function renderApp(initialRoute = '/') {
  return render(
    <MemoryRouter initialEntries={[initialRoute]}>
      <AppShell />
    </MemoryRouter>
  );
}

describe('App navigation', () => {
  it('renders the brand name', () => {
    renderApp();
    expect(screen.getByText('Pipeline Console')).toBeDefined();
  });

  it('renders Case Generation nav button', () => {
    renderApp();
    expect(screen.getByRole('button', { name: 'Case Generation' })).toBeDefined();
  });

  it('renders Prompt Learning nav button', () => {
    renderApp();
    expect(screen.getByRole('button', { name: 'Prompt Learning' })).toBeDefined();
  });

  it('highlights Case Generation as active on the home route', () => {
    renderApp('/');
    const btn = screen.getByRole('button', { name: 'Case Generation' });
    expect(btn.className).toContain('active');
  });

  it('highlights Prompt Learning as active on /prompt-learning', () => {
    renderApp('/prompt-learning');
    const btn = screen.getByRole('button', { name: 'Prompt Learning' });
    expect(btn.className).toContain('active');
  });

  it('switches active state when navigating between pages', async () => {
    renderApp('/prompt-learning');
    const plBtn = screen.getByRole('button', { name: 'Prompt Learning' });
    const cgBtn = screen.getByRole('button', { name: 'Case Generation' });
    expect(plBtn.className).toContain('active');

    // Navigate back to case generation
    cgBtn.click();
    await waitFor(() => {
      expect(cgBtn.className).toContain('active');
      expect(plBtn.className).not.toContain('active');
    });
  });

  it('shows Prompt Learning page header at /prompt-learning', () => {
    renderApp('/prompt-learning');
    expect(screen.getByRole('heading', { name: 'Prompt Learning', level: 1 })).toBeDefined();
  });

  it('Case Generation routes show Home page content', async () => {
    renderApp('/');
    await waitFor(() => {
      expect(screen.getByPlaceholderText('Search requirements... (/)')).toBeDefined();
    });
  });
});
