import type { RunInfo } from '../api/types'

interface StageDef {
  key: string
  label: string
  artifact: string
}

const STAGES: StageDef[] = [
  { key: 'extraction', label: 'Extraction', artifact: 'extracted_test_basis.json' },
  { key: 'intents', label: 'Case Intents', artifact: 'case_intents.json' },
  { key: 'cases', label: 'Cases', artifact: 'generated_cases.json' },
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
      case 'extraction':
        return artifacts.has('extracted_test_basis.json')
      case 'intents':
        return artifacts.has('case_intents.json')
      case 'cases':
        return true // Always available — shows results if cases exist
      default:
        return false
    }
  }

  const missingReason = (stage: StageDef): string => {
    if (isAvailable(stage)) return ''
    switch (stage.key) {
      case 'extraction':
        return 'Start a run or wait for extraction'
      case 'intents':
        return 'Complete Extraction review and plan intents'
      case 'cases':
        return 'Not available'
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
