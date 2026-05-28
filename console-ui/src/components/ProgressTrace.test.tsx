import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import ProgressTrace from './ProgressTrace'

vi.mock('../api/endpoints', () => ({
  getTrace: vi.fn(),
}))

import { getTrace } from '../api/endpoints'
import type { TraceData } from '../api/types'

const mockTrace: TraceData = {
  run_dir: 'test-run',
  events: [
    {
      timestamp: 1716829200,
      stage: 'extraction',
      event: 'stage_started',
      message: 'Starting requirement extraction',
    },
    {
      timestamp: 1716829201,
      stage: 'extraction',
      event: 'llm_done',
      provider: 'ollama',
      model: 'qwen2.5:7b',
      duration_ms: 1500,
      message: 'Requirement extraction complete',
    },
    {
      timestamp: 1716829202,
      stage: 'extraction',
      event: 'artifact_written',
      message: 'Written extracted_test_basis.json',
    },
    {
      timestamp: 1716829203,
      stage: 'extraction',
      event: 'completed',
      message: 'Extraction review ready',
    },
  ],
}

function renderTrace(override?: Partial<TraceData>) {
  const data = { ...mockTrace, ...override }
  ;(getTrace as ReturnType<typeof vi.fn>).mockResolvedValue(data)
  return render(<ProgressTrace runDir="test-run" />)
}

describe('ProgressTrace', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders loading state initially', () => {
    ;(getTrace as ReturnType<typeof vi.fn>).mockImplementation(
      () => new Promise(() => {}) // never resolves
    )
    render(<ProgressTrace runDir="test-run" />)
    expect(screen.getByText('Loading...')).toBeInTheDocument()
  })

  it('renders trace events', async () => {
    renderTrace()
    await waitFor(() => {
      expect(screen.getByText('Starting requirement extraction')).toBeInTheDocument()
    })
  })

  it('shows event count in header', async () => {
    renderTrace()
    await waitFor(() => {
      expect(screen.getByText(/Progress Trace \(4 events\)/)).toBeInTheDocument()
    })
  })

  it('renders stage labels for each event', async () => {
    renderTrace()
    await waitFor(() => {
      expect(screen.getAllByText('Extraction').length).toBeGreaterThanOrEqual(4)
    })
  })

  it('renders provider and model info', async () => {
    renderTrace()
    await waitFor(() => {
      expect(screen.getByText(/ollama/)).toBeInTheDocument()
      expect(screen.getByText(/qwen2.5:7b/)).toBeInTheDocument()
    })
  })

  it('shows duration in seconds', async () => {
    renderTrace()
    await waitFor(() => {
      expect(screen.getByText(/1\.5\s*s/)).toBeInTheDocument()
    })
  })

  it('shows graceful message for empty events', async () => {
    ;(getTrace as ReturnType<typeof vi.fn>).mockResolvedValue({
      run_dir: 'test-run',
      events: [],
    })
    render(<ProgressTrace runDir="test-run" />)
    await waitFor(() => {
      expect(screen.getByText(/No trace events recorded/)).toBeInTheDocument()
    })
  })

  it('shows graceful message when trace endpoint fails', async () => {
    ;(getTrace as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('Not found'))
    render(<ProgressTrace runDir="test-run" />)
    await waitFor(() => {
      expect(screen.getByText(/Trace data not available/)).toBeInTheDocument()
    })
  })

  it('renders event type labels', async () => {
    renderTrace()
    await waitFor(() => {
      expect(screen.getByText('stage_started')).toBeInTheDocument()
      expect(screen.getByText('llm_done')).toBeInTheDocument()
    })
  })
})
