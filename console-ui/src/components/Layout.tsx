import { Outlet } from 'react-router-dom'
import JobBanner from './JobBanner'
import { useJob } from '../hooks/JobContext'

export default function Layout() {
  const { job, status, startPolling: retry } = useJob()

  return (
    <div className="console-shell">
      <header className="console-header">
        <h1>Pipeline Console</h1>
      </header>
      <JobBanner job={job} status={status} onRetry={retry} />
      <main className="console-main">
        <Outlet />
      </main>
    </div>
  )
}
