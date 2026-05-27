import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import RequirementsTable from './RequirementsTable'

const sampleReqs = [
  { id: 0, requirement_key: 'REQ-001', description: 'Test requirement one', function_name: 'fn1', requirement_type: 'requirement', supplementary_info: '', is_heading: false, is_info: false },
  { id: 1, requirement_key: 'REQ-002', description: 'Another requirement', function_name: '', requirement_type: 'info', supplementary_info: '', is_heading: false, is_info: true },
  { id: 2, requirement_key: 'REQ-HEAD', description: 'Section heading', function_name: '', requirement_type: 'heading', supplementary_info: '', is_heading: true, is_info: false },
]

describe('RequirementsTable', () => {
  it('renders requirement keys in the table', () => {
    const runMap = new Map()
    render(
      <MemoryRouter>
        <RequirementsTable requirements={sampleReqs} runMap={runMap} />
      </MemoryRouter>
    )
    expect(screen.getByText('REQ-001')).toBeInTheDocument()
  })

  it('filters out headings and info rows', () => {
    const runMap = new Map()
    render(
      <MemoryRouter>
        <RequirementsTable requirements={sampleReqs} runMap={runMap} />
      </MemoryRouter>
    )
    expect(screen.getByText('REQ-001')).toBeInTheDocument()
    expect(screen.queryByText('REQ-002')).not.toBeInTheDocument()
    expect(screen.queryByText('REQ-HEAD')).not.toBeInTheDocument()
  })

  it('shows run status when available', () => {
    const runMap = new Map([
      ['REQ-001', { status: 'evaluated', time: '2026-01-01T00:00:00', dir: 'run-1' }],
    ])
    render(
      <MemoryRouter>
        <RequirementsTable requirements={sampleReqs} runMap={runMap} />
      </MemoryRouter>
    )
    expect(screen.getByText('Evaluated')).toBeInTheDocument()
    expect(screen.getByText('Open Latest Run')).toBeInTheDocument()
  })

  it('shows "No runs" when no run exists', () => {
    const runMap = new Map()
    render(
      <MemoryRouter>
        <RequirementsTable requirements={sampleReqs} runMap={runMap} />
      </MemoryRouter>
    )
    expect(screen.getByText('No runs')).toBeInTheDocument()
  })

  it('shows requirement count excluding headings', () => {
    const runMap = new Map()
    render(
      <MemoryRouter>
        <RequirementsTable requirements={sampleReqs} runMap={runMap} />
      </MemoryRouter>
    )
    expect(screen.getByText('Requirements (1)')).toBeInTheDocument()
  })
})
