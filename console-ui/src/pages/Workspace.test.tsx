import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { JobProvider } from '../hooks/JobContext'

const mockRefetch = vi.fn()
let mockRun: {
  run_dir: string
  requirement_key: string
  description: string
  status: string
  artifacts: string[]
} | null = null

vi.mock('../hooks/useRun', () => ({
  useRun: () => ({
    run: mockRun,
    loading: false,
    error: null,
    refetch: mockRefetch,
  }),
}))

vi.mock('../hooks/useMode', () => ({
  useMode: () => ({
    mode: { provider: 'mock', model: 'mock', mock_mode: true },
    loading: false,
    error: null,
  }),
}))

vi.mock('./ExtractionReviewPage', () => ({
  default: ({ runDir, onAdvanced }: { runDir: string; onAdvanced?: () => void }) => (
    <div data-testid="extraction-page">Extraction: {runDir}</div>
  ),
}))
vi.mock('./IntentReviewPage', () => ({
  default: ({ runDir }: { runDir: string }) => <div data-testid="intents-page">Intents: {runDir}</div>,
}))
vi.mock('./ResultsPage', () => ({
  default: ({ runDir }: { runDir: string }) => <div data-testid="cases-page">Cases: {runDir}</div>,
}))

import Workspace from './Workspace'

function renderWorkspace(runDir: string) {
  return render(
    <MemoryRouter initialEntries={[`/run/${runDir}`]}>
      <JobProvider>
        <Routes>
          <Route path="/run/:runDir" element={<Workspace />} />
        </Routes>
      </JobProvider>
    </MemoryRouter>
  )
}

describe('Workspace stage switching', () => {
  beforeEach(() => {
    mockRefetch.mockClear()
    mockRun = null
  })

  it('auto-selects cases stage when run has generated_cases', async () => {
    mockRun = {
      run_dir: 'run-test',
      requirement_key: 'REQ-001',
      description: 'Test requirement',
      status: 'cases_reviewed',
      artifacts: [
        '00_requirements.json',
        'extracted_test_basis.json',
        'case_intents.json',
        'generated_cases.json',
        'reviewed_cases.json',
      ],
    }
    renderWorkspace('run-test')
    await screen.findByTestId('cases-page')
    expect(screen.getByTestId('cases-page')).toBeInTheDocument()
  })

  it('preserves user-selected stage across refetch on completed run', async () => {
    mockRun = {
      run_dir: 'run-test',
      requirement_key: 'REQ-001',
      description: 'Test requirement',
      status: 'cases_reviewed',
      artifacts: [
        '00_requirements.json',
        'extracted_test_basis.json',
        'case_intents.json',
        'generated_cases.json',
        'reviewed_cases.json',
      ],
    }
    renderWorkspace('run-test')

    // Initially auto-selects cases
    await screen.findByTestId('cases-page')

    // User manually switches to Extraction
    const extractionBtn = screen.getByText('Extraction')
    await userEvent.click(extractionBtn)

    // Should now show extraction page
    expect(screen.getByTestId('extraction-page')).toBeInTheDocument()

    // Trigger handleStageChange again (which also calls refetchRun)
    const intentsBtn = screen.getByText('Case Intents')
    await userEvent.click(intentsBtn)

    // Should show intents, not reset back to cases
    expect(screen.getByTestId('intents-page')).toBeInTheDocument()
    expect(screen.queryByTestId('cases-page')).not.toBeInTheDocument()
  })

  it('shows all stages as enabled when artifacts exist', async () => {
    mockRun = {
      run_dir: 'run-test',
      requirement_key: 'REQ-001',
      description: 'Test requirement',
      status: 'cases_reviewed',
      artifacts: [
        'extracted_test_basis.json',
        'case_intents.json',
        'generated_cases.json',
      ],
    }
    renderWorkspace('run-test')
    await screen.findByTestId('cases-page')

    expect(screen.getByText('Extraction').closest('button')).not.toBeDisabled()
    expect(screen.getByText('Case Intents').closest('button')).not.toBeDisabled()
    expect(screen.getByText('Cases').closest('button')).not.toBeDisabled()
  })

  it('shows future stages as disabled when artifacts are missing', async () => {
    mockRun = {
      run_dir: 'run-test',
      requirement_key: 'REQ-001',
      description: 'Test requirement',
      status: 'extraction_pending_review',
      artifacts: [
        '00_requirements.json',
        'extracted_test_basis.json',
      ],
    }
    renderWorkspace('run-test')

    // Wait for the component to render
    await screen.findByText('REQ-001')

    expect(screen.getByText('Case Intents').closest('button')).toBeDisabled()
    // Cases stage is always available
    expect(screen.getByText('Cases').closest('button')).not.toBeDisabled()
  })
})
