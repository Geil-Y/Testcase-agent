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

vi.mock('./ClarificationReviewPage', () => ({
  default: ({ runDir }: { runDir: string }) => <div data-testid="clarification-page">Clarification: {runDir}</div>,
}))
vi.mock('./IntentReviewPage', () => ({
  default: ({ runDir }: { runDir: string }) => <div data-testid="intents-page">Intents: {runDir}</div>,
}))
vi.mock('./ResultsPage', () => ({
  default: ({ runDir }: { runDir: string }) => <div data-testid="results-page">Results: {runDir}</div>,
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

  it('auto-selects results stage when run has generated_cases', async () => {
    mockRun = {
      run_dir: 'run-test',
      requirement_key: 'REQ-001',
      description: 'Test requirement',
      status: 'evaluated',
      artifacts: [
        '00_requirements.json',
        'clarification_review.json',
        'clarified_test_basis.json',
        'case_intent_review.json',
        'approved_case_plan.json',
        'generated_cases.json',
        'evaluation_summary.json',
      ],
    }
    renderWorkspace('run-test')
    await screen.findByTestId('results-page')
    expect(screen.getByTestId('results-page')).toBeInTheDocument()
  })

  it('preserves user-selected stage across refetch on completed run', async () => {
    mockRun = {
      run_dir: 'run-test',
      requirement_key: 'REQ-001',
      description: 'Test requirement',
      status: 'evaluated',
      artifacts: [
        '00_requirements.json',
        'clarification_review.json',
        'case_intent_review.json',
        'generated_cases.json',
        'evaluation_summary.json',
      ],
    }
    renderWorkspace('run-test')

    // Initially auto-selects results
    await screen.findByTestId('results-page')

    // User manually switches to Clarification Review
    const clarificationBtn = screen.getByText('Clarification Review')
    await userEvent.click(clarificationBtn)

    // Should now show clarification page
    expect(screen.getByTestId('clarification-page')).toBeInTheDocument()

    // Trigger handleStageChange again (which also calls refetchRun)
    const intentsBtn = screen.getByText('Case Intent Review')
    await userEvent.click(intentsBtn)

    // Should show intents, not reset back to results
    expect(screen.getByTestId('intents-page')).toBeInTheDocument()
    expect(screen.queryByTestId('results-page')).not.toBeInTheDocument()
  })

  it('shows all stages as enabled when artifacts exist', async () => {
    mockRun = {
      run_dir: 'run-test',
      requirement_key: 'REQ-001',
      description: 'Test requirement',
      status: 'evaluated',
      artifacts: [
        'clarification_review.json',
        'case_intent_review.json',
        'generated_cases.json',
      ],
    }
    renderWorkspace('run-test')
    await screen.findByTestId('results-page')

    expect(screen.getByText('Clarification Review').closest('button')).not.toBeDisabled()
    expect(screen.getByText('Case Intent Review').closest('button')).not.toBeDisabled()
    expect(screen.getByText('Results').closest('button')).not.toBeDisabled()
  })

  it('shows future stages as disabled when artifacts are missing', async () => {
    mockRun = {
      run_dir: 'run-test',
      requirement_key: 'REQ-001',
      description: 'Test requirement',
      status: 'clarification_ready',
      artifacts: [
        '00_requirements.json',
        'clarification_review.json',
      ],
    }
    renderWorkspace('run-test')

    // Wait for the component to render
    await screen.findByText('REQ-001')

    expect(screen.getByText('Case Intent Review').closest('button')).toBeDisabled()
    expect(screen.getByText('Results').closest('button')).toBeDisabled()
  })
})
