import { useState, useRef } from 'react'
import { previewExcel, confirmImport } from '../api/endpoints'
import type { PreviewResult, ImportBatch } from '../api/types'

interface Props {
  onImported: (batch: ImportBatch) => void
}

export default function ImportSection({ onImported }: Props) {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<PreviewResult | null>(null)
  const [mapping, setMapping] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [importing, setImporting] = useState(false)
  const [sheet, setSheet] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (!f) return
    setFile(f)
    setError(null)
    setUploading(true)
    try {
      const p = await previewExcel(f)
      setPreview(p)
      setSheet(p.sheets[0] || '')
      setMapping({})
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Preview failed')
    } finally {
      setUploading(false)
    }
  }

  const handleConfirm = async () => {
    if (!preview) return
    setImporting(true)
    setError(null)
    try {
      const batch = await confirmImport({
        tmp_path: preview.tmp_path,
        sheet: sheet || null,
        mapping,
        filename: file?.name || 'upload.xlsx',
      })
      setPreview(null)
      setFile(null)
      if (fileRef.current) fileRef.current.value = ''
      onImported(batch)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Import failed')
    } finally {
      setImporting(false)
    }
  }

  const updateMapping = (key: string, value: string) => {
    setMapping((prev) => ({ ...prev, [key]: value }))
  }

  return (
    <div className="card import-section">
      <h3>Import Requirements</h3>

      <div className="import-upload">
        <input
          type="file"
          accept=".xlsx,.xls"
          onChange={handleFile}
          ref={fileRef}
          disabled={uploading || importing}
        />
        {uploading && <span>Reading file...</span>}
      </div>

      {error && <div className="error-msg">{error}</div>}

      {preview && (
        <div className="import-preview">
          <h4>Column Mapping</h4>
          <p className="text-muted">File: {preview.filename}</p>

          {preview.sheets.length > 1 && (
            <div className="form-group">
              <label>Sheet</label>
              <select value={sheet} onChange={(e) => setSheet(e.target.value)}>
                {preview.sheets.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
          )}

          <div className="mapping-grid">
            {(['requirement_key_col', 'description_col', 'function_name_col', 'requirement_type_col'] as const).map((key) => (
              <div key={key} className="form-group">
                <label>{key.replace(/_col$/, '').replace(/_/g, ' ')}</label>
                <select
                  value={mapping[key] || ''}
                  onChange={(e) => updateMapping(key, e.target.value)}
                >
                  <option value="">-- Select column --</option>
                  {preview.columns.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </div>
            ))}
          </div>

          <div className="import-actions">
            <button
              className="btn btn-primary"
              onClick={handleConfirm}
              disabled={importing || !mapping.requirement_key_col || !mapping.description_col}
            >
              {importing ? 'Importing...' : 'Confirm Import'}
            </button>
            <button
              className="btn"
              onClick={() => { setPreview(null); setFile(null); if (fileRef.current) fileRef.current.value = '' }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
