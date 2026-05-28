import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import StageNav from '../components/StageNav'
import ModeBadge from '../components/ModeBadge'
import ProgressTrace from '../components/ProgressTrace'
import ExtractionReviewPage from './ExtractionReviewPage'
import IntentReviewPage from './IntentReviewPage'
import ResultsPage from './ResultsPage'
import { useRun } from '../hooks/useRun'
import { useJob } from '../hooks/JobContext'

const STATUS_LABELS: Record<string, string> = {
  new: 'New',
  extraction_pending_review: 'Extraction Pending Review',
  extraction_reviewed: 'Extraction Reviewed',
  extraction_blocked: 'Extraction Blocked',
  intents_pending_review: 'Intents Pending Review',
  intents_reviewed: 'Intents Reviewed',
  intents_blocked: 'Intents Blocked',
  cases_pending_review: 'Cases Pending Review',
  cases_reviewed: 'Cases Reviewed',
  legacy_unsupported: 'Legacy (Unsupported)',
  failed: 'Failed',
}

function determineStage(artifacts: Set<string>): string {
  if (artifacts.has('generated_cases.json') || artifacts.has('reviewed_cases.json')) return 'cases'
  if (artifacts.has('case_intents.json')) return 'intents'
  if (artifacts.has('extracted_test_basis.json')) return 'extraction'
  return 'extraction'
}

export default function Workspace() {
  const { runDir } = useParams<{ runDir: string }>()
  const navigate = useNavigate()
  const { run, loading, error, refetch: refetchRun } = useRun(runDir)
  const { isLocked } = useJob()
  const [activeStage, setActiveStage] = useState('extraction')
  const [userSelectedStage, setUserSelectedStage] = useState(false)

  useEffect(() => {
    if (run && !userSelectedStage) {
      const arts = new Set(run.artifacts || [])
      setActiveStage(determineStage(arts))
    }
  }, [run, userSelectedStage])

  if (loading) return <div className="workspace"><p>Loading run...</p></div>
  if (error) return <div className="workspace"><div className="error-msg">{error}</div></div>
  if (!run) return <div className="workspace"><div className="error-msg">Run not found</div></div>

  const handleStageChange = (stage: string) => {
    setUserSelectedStage(true)
    setActiveStage(stage)
    refetchRun()
  }

  return (
    <div className="workspace">
      <div className="workspace-header">
        <button className="btn btn-sm" onClick={() => navigate('/')}>
          &larr; Back to Home
        </button>
        <div className="workspace-meta">
          <h2>{run.requirement_key}</h2>
          <p className="text-muted">{run.description?.slice(0, 120)}</p>
          <div className="workspace-info">
            <span><strong>Run:</strong> {run.run_dir}</span>
            <span className={`badge badge-status-${run.status}`}>
              {STATUS_LABELS[run.status] || run.status}
            </span>
            <ModeBadge />
            {isLocked && <span className="badge badge-mock">Actions Locked</span>}
          </div>
        </div>
      </div>

      <div className="workspace-body">
        <StageNav run={run} activeStage={activeStage} onStageClick={handleStageChange} />

        <div className="workspace-content">
          {activeStage === 'extraction' && runDir && (
            <ExtractionReviewPage
              runDir={runDir}
              onAdvanced={() => { refetchRun(); setActiveStage('intents') }}
            />
          )}
          {activeStage === 'intents' && runDir && (
            <IntentReviewPage runDir={runDir} />
          )}
          {activeStage === 'cases' && runDir && (
            <ResultsPage runDir={runDir} />
          )}
        </div>
      </div>

      {runDir && (
        <div style={{ marginTop: 24 }}>
          <ProgressTrace runDir={runDir} />
        </div>
      )}
    </div>
  )
}
