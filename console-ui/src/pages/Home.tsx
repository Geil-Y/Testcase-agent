import { useEffect } from 'react'
import ModeBadge from '../components/ModeBadge'
import ImportSection from '../components/ImportSection'
import BatchSelector from '../components/BatchSelector'
import RequirementsTable from '../components/RequirementsTable'
import { useImportBatches } from '../hooks/useImportBatches'
import { useRuns } from '../hooks/useRuns'
import { useEnrichedRequirements } from '../hooks/useEnrichedRequirements'

export default function Home() {
  const { batches, selectedBatch, loading, error, loadLatest, loadBatch, refetchBatches } = useImportBatches()
  const { runs, refetch: refetchRuns } = useRuns()
  const runMap = useEnrichedRequirements(selectedBatch?.requirements, runs)

  useEffect(() => {
    loadLatest()
  }, [loadLatest])

  const handleImported = () => {
    refetchBatches()
    loadLatest()
  }

  return (
    <div className="home">
      <div className="home-header">
        <h2>Pipeline Console</h2>
        <ModeBadge />
      </div>

      <div className="home-grid">
        <div className="home-sidebar">
          <ImportSection onImported={handleImported} />
          <BatchSelector
            batches={batches}
            selectedId={selectedBatch?.id || null}
            onSelect={loadBatch}
          />
          <button className="btn btn-sm" onClick={() => { refetchBatches(); refetchRuns(); }}>
            Refresh
          </button>
        </div>

        <div className="home-main">
          {loading && <p>Loading batch...</p>}
          {error && <div className="error-msg">{error}</div>}

          {selectedBatch && (
            <RequirementsTable
              requirements={selectedBatch.requirements}
              runMap={runMap}
              batchId={selectedBatch.id}
            />
          )}

          {!loading && !error && !selectedBatch && (
            <div className="card">
              <p className="text-muted">Import an Excel file to get started, or select a recent batch.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
