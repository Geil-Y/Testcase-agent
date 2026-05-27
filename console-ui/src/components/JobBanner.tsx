import { retryJob } from '../api/endpoints'

interface Props {
  job: { id?: string; name?: string; error?: string | null; error_detail?: string | null } | null
  status: 'idle' | 'running' | 'succeeded' | 'failed' | 'retryable'
  onRetry?: () => void
}

export default function JobBanner({ job, status, onRetry }: Props) {
  if (status === 'idle' || !job) return null

  const bannerClass = status === 'running' ? 'job-banner-running'
    : status === 'succeeded' ? 'job-banner-succeeded'
    : 'job-banner-failed'

  const handleRetry = async () => {
    try {
      await retryJob()
      onRetry?.()
    } catch {
      // error state handled by polling
    }
  }

  return (
    <div className={`job-banner ${bannerClass}`}>
      {status === 'running' && (
        <>
          <span className="spinner" />
          <span>Running: {job.name || 'Job'}...</span>
        </>
      )}
      {status === 'succeeded' && (
        <span>Completed: {job.name || 'Job'}</span>
      )}
      {(status === 'failed' || status === 'retryable') && (
        <>
          <span>Failed: {job.name || 'Job'}</span>
          {job.error && <code className="job-error">{job.error}</code>}
          <button className="btn btn-sm" onClick={handleRetry}>
            Retry
          </button>
        </>
      )}
    </div>
  )
}
