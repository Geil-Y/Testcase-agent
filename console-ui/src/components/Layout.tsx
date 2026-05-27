import { Outlet } from 'react-router-dom'
import JobBanner from './JobBanner'

export default function Layout() {
  return (
    <div className="console-shell">
      <header className="console-header">
        <h1>Pipeline Console</h1>
      </header>
      <JobBanner />
      <main className="console-main">
        <Outlet />
      </main>
    </div>
  )
}
