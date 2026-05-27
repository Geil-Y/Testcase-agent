import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import StageNav from '../components/StageNav'
import ModeBadge from '../components/ModeBadge'
import ClarificationReviewPage from './ClarificationReviewPage'
import IntentReviewPage from './IntentReviewPage'
import ResultsPage from './ResultsPage'
import { useRun } from '../hooks/useRun'
import { useJob } from '../hooks/JobContext'

const STATUS_LABELS: Record<string, string> = {
  evaluated: 'Evaluated',
  cases_ready: 'Cases Ready',
  intent_ready: 'Intent Ready',
  clarification_ready: 'Clarification Ready',
  clarification_blocked: 'Blocked',
  new: 'New',
  failed: 'Failed',
}

function determineStage(artifacts: Set<string>): string {
  if (artifacts.has('generated_cases.json') || artifacts.has('evaluation_summary.json')) return 'results'
  if (artifacts.has('case_intent_review.json')) return 'intents'
  return 'clarification'
}

export default function Workspace() {
  const { runDir } = useParams<{ runDir: string }>()
  const navigate = useNavigate()
  const { run, loading, error, refetch: refetchRun } = useRun(runDir)
  const { isLocked } = useJob()
  const [activeStage, setActiveStage] = useState('clarification')

  useEffect(() => {
    if (run) {
      const arts = new Set(run.artifacts || [])
      setActiveStage(determineStage(arts))
    }
  }, [run])

  if (loading) return <div className="workspace"><p>Loading run...</p></div>
  if (error) return <div className="workspace"><div className="error-msg">{error}</div></div>
  if (!run) return <div className="workspace"><div className="error-msg">Run not found</div></div>

  const handleStageChange = (stage: string) => {
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
          {activeStage === 'clarification' && runDir && (
            <ClarificationReviewPage
              runDir={runDir}
              onAdvanced={() => { refetchRun(); setActiveStage('intents') }}
            />
          )}
          {activeStage === 'intents' && runDir && (
            <IntentReviewPage runDir={runDir} />
          )}
          {activeStage === 'results' && runDir && (
            <ResultsPage runDir={runDir} />
          )}
        </div>
      </div>
    </div>
  )
}
