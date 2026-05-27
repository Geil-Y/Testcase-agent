import type { RunInfo } from '../api/types'

interface StageDef {
  key: string
  label: string
  artifact: string
}

const STAGES: StageDef[] = [
  { key: 'clarification', label: 'Clarification Review', artifact: 'clarification_review.json' },
  { key: 'intents', label: 'Case Intent Review', artifact: 'case_intent_review.json' },
  { key: 'results', label: 'Results', artifact: 'generated_cases.json' },
]

interface Props {
  run: RunInfo
  activeStage: string
  onStageClick: (stage: string) => void
}

export default function StageNav({ run, activeStage, onStageClick }: Props) {
  const artifacts = new Set(run.artifacts || [])

  const isAvailable = (stage: StageDef): boolean => {
    switch (stage.key) {
      case 'clarification':
        return artifacts.has('clarification_review.json')
      case 'intents':
        return artifacts.has('case_intent_review.json') || artifacts.has('clarified_test_basis.json')
      case 'results':
        return artifacts.has('generated_cases.json') || artifacts.has('evaluation_summary.json')
      default:
        return false
    }
  }

  const missingReason = (stage: StageDef): string => {
    if (isAvailable(stage)) return ''
    switch (stage.key) {
      case 'clarification':
        return 'Start a run or prepare clarification review'
      case 'intents':
        return 'Complete Clarification Review and advance'
      case 'results':
        return 'Complete Case Intent Review and generate cases'
      default:
        return 'Not available'
    }
  }

  return (
    <nav className="stage-nav">
      <h3>Stages</h3>
      {STAGES.map((s) => {
        const avail = isAvailable(s)
        return (
          <button
            key={s.key}
            className={`stage-nav-item ${s.key === activeStage ? 'active' : ''} ${!avail ? 'disabled' : ''}`}
            disabled={!avail}
            onClick={() => onStageClick(s.key)}
            title={!avail ? missingReason(s) : ''}
          >
            <span className="stage-label">{s.label}</span>
            {!avail && <span className="stage-hint">{missingReason(s)}</span>}
          </button>
        )
      })}
    </nav>
  )
}
