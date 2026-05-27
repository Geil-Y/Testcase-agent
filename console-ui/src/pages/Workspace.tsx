import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import StageNav from '../components/StageNav'
import ModeBadge from '../components/ModeBadge'
import ClarificationReviewPage from './ClarificationReviewPage'
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
  const { run, loading, error } = useRun(runDir)
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
        <StageNav run={run} activeStage={activeStage} onStageClick={setActiveStage} />

        <div className="workspace-content">
          {activeStage === 'clarification' && runDir && (
            <ClarificationReviewPage runDir={runDir} />
          )}
          {activeStage === 'intents' && (
            <div className="card">
              <h3>Case Intent Review</h3>
              <p className="text-muted">Case intent workbench — see #24.</p>
            </div>
          )}
          {activeStage === 'results' && (
            <div className="card">
              <h3>Results</h3>
              <p className="text-muted">Read-only results — see #27.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
