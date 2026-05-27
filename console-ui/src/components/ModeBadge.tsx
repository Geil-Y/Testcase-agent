import { useMode } from '../hooks/useMode'

export default function ModeBadge() {
  const { mode } = useMode()
  if (!mode) return null

  return (
    <span className={`badge ${mode.is_mock ? 'badge-mock' : 'badge-real'}`}>
      {mode.label}
    </span>
  )
}
