import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { JobProvider } from './hooks/JobContext'
import App from './App'

function renderApp(initialEntries: string[] = ['/']) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <JobProvider>
        <App />
      </JobProvider>
    </MemoryRouter>
  )
}

describe('Console shell', () => {
  it('renders the shell header with title', () => {
    renderApp()
    const headings = screen.getAllByText('Pipeline Console')
    expect(headings.length).toBeGreaterThanOrEqual(1)
    expect(screen.getByRole('banner')).toBeInTheDocument()
  })

  it('renders home page with import section', () => {
    renderApp()
    expect(screen.getByText('Import Requirements')).toBeInTheDocument()
  })

  it('renders workspace loading state for run route', () => {
    renderApp(['/run/test-run-001'])
    expect(screen.getByText('Loading run...')).toBeInTheDocument()
  })
})
