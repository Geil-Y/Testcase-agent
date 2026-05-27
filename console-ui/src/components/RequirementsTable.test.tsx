import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { JobProvider } from '../hooks/JobContext'
import RequirementsTable from './RequirementsTable'

const sampleReqs = [
  { id: 0, requirement_key: 'REQ-001', description: 'Test requirement one', function_name: 'fn1', requirement_type: 'requirement', supplementary_info: '', is_heading: false, is_info: false },
  { id: 1, requirement_key: 'REQ-002', description: 'Another requirement', function_name: '', requirement_type: 'info', supplementary_info: '', is_heading: false, is_info: true },
  { id: 2, requirement_key: 'REQ-HEAD', description: 'Section heading', function_name: '', requirement_type: 'heading', supplementary_info: '', is_heading: true, is_info: false },
]

function renderTable(runMap: Map<string, { status: string; time: string; dir: string }>) {
  return render(
    <MemoryRouter>
      <JobProvider>
        <RequirementsTable requirements={sampleReqs} runMap={runMap} batchId="test-batch" />
      </JobProvider>
    </MemoryRouter>
  )
}

describe('RequirementsTable', () => {
  it('renders requirement keys in the table', () => {
    renderTable(new Map())
    expect(screen.getByText('REQ-001')).toBeInTheDocument()
  })

  it('filters out headings and info rows', () => {
    renderTable(new Map())
    expect(screen.getByText('REQ-001')).toBeInTheDocument()
    expect(screen.queryByText('REQ-002')).not.toBeInTheDocument()
    expect(screen.queryByText('REQ-HEAD')).not.toBeInTheDocument()
  })

  it('shows run status when available', () => {
    const runMap = new Map([
      ['REQ-001', { status: 'evaluated', time: '2026-01-01T00:00:00', dir: 'run-1' }],
    ])
    renderTable(runMap)
    expect(screen.getByText('Evaluated')).toBeInTheDocument()
    expect(screen.getByText('Open')).toBeInTheDocument()
  })

  it('shows "No runs" when no run exists', () => {
    renderTable(new Map())
    expect(screen.getByText('No runs')).toBeInTheDocument()
  })

  it('shows Start New Run button', () => {
    renderTable(new Map())
    expect(screen.getByText('Start New Run')).toBeInTheDocument()
  })

  it('shows requirement count excluding headings', () => {
    renderTable(new Map())
    expect(screen.getByText('Requirements (1)')).toBeInTheDocument()
  })
})
