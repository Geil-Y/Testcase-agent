import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import App from './App'

describe('Console shell', () => {
  it('renders the shell header with title', () => {
    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>
    )
    const headings = screen.getAllByText('Pipeline Console')
    expect(headings.length).toBeGreaterThanOrEqual(1)
    expect(screen.getByRole('banner')).toBeInTheDocument()
  })

  it('renders home page by default', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>
    )
    expect(screen.getByText('Loading Console...')).toBeInTheDocument()
  })

  it('renders workspace for run route', () => {
    render(
      <MemoryRouter initialEntries={['/run/test-run-001']}>
        <App />
      </MemoryRouter>
    )
    expect(screen.getByText('Active Run Workspace')).toBeInTheDocument()
  })
})
