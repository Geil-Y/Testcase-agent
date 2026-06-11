import { useState, useEffect, useRef, useCallback } from 'react';
import { inspectWorkbooks } from '../api/pl-api';
import type { WorkbookInspection, RequirementColMap, RefTestCaseColMap } from '../api/pl-types';

const LS_KEY = 'pl_column_mapping';

interface StoredMapping {
  reqSheet: string;
  caseSheets: string[];
  reqCols: RequirementColMap;
  caseCols: RefTestCaseColMap;
}

function loadStoredMapping(): StoredMapping | null {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as StoredMapping;
  } catch {
    return null;
  }
}

function saveMapping(mapping: StoredMapping) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(mapping));
  } catch {
    // ignore quota errors silently
  }
}

/** Sanitize a column mapping against currently available columns —
 *  clear fields that reference columns no longer present. */
function sanitizeReqCols(cols: RequirementColMap, available: Set<string>): RequirementColMap {
  return {
    requirementKey: available.has(cols.requirementKey) ? cols.requirementKey : '',
    description: available.has(cols.description) ? cols.description : '',
    functionName: cols.functionName && available.has(cols.functionName) ? cols.functionName : undefined,
    requirementType: cols.requirementType && available.has(cols.requirementType) ? cols.requirementType : undefined,
  };
}

function sanitizeCaseCols(cols: RefTestCaseColMap, available: Set<string>): RefTestCaseColMap {
  return {
    caseId: cols.caseId && available.has(cols.caseId) ? cols.caseId : undefined,
    linkedRequirements: available.has(cols.linkedRequirements) ? cols.linkedRequirements : '',
    title: available.has(cols.title) ? cols.title : '',
    action: available.has(cols.action) ? cols.action : '',
    expectedResult: available.has(cols.expectedResult) ? cols.expectedResult : '',
    objective: cols.objective && available.has(cols.objective) ? cols.objective : undefined,
  };
}

export default function PromptLearning() {
  // ── File upload state ──
  const [reqFile, setReqFile] = useState<File | null>(null);
  const [caseFile, setCaseFile] = useState<File | null>(null);
  const [inspecting, setInspecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ── Inspection results ──
  const [reqInspect, setReqInspect] = useState<WorkbookInspection | null>(null);
  const [caseInspect, setCaseInspect] = useState<WorkbookInspection | null>(null);

  // ── Sheet selection ──
  const [reqSheet, setReqSheet] = useState('');
  const [caseSheets, setCaseSheets] = useState<string[]>([]);

  // ── Column mapping ──
  const [reqCols, setReqCols] = useState<RequirementColMap>({ requirementKey: '', description: '' });
  const [caseCols, setCaseCols] = useState<RefTestCaseColMap>({ linkedRequirements: '', title: '', action: '', expectedResult: '' });

  // ── Track whether we've attempted restore ──
  const [restored, setRestored] = useState(false);

  // ── Ref for hidden file inputs ──
  const reqInputRef = useRef<HTMLInputElement>(null);
  const caseInputRef = useRef<HTMLInputElement>(null);

  // ── Derived: columns for the currently selected sheet ──
  const reqColumns = reqInspect?.sheets.find(s => s.name === reqSheet)?.columns ?? [];
  const caseColumns = caseInspect?.sheets.length ? caseInspect.sheets[0]?.columns ?? [] : [];

  // ── Persist to localStorage whenever mapping changes ──
  useEffect(() => {
    if (!restored) return; // don't save until initial restore is done
    saveMapping({ reqSheet, caseSheets, reqCols, caseCols });
  }, [reqSheet, caseSheets, reqCols, caseCols, restored]);

  // ── Restore from localStorage when inspection results arrive ──
  useEffect(() => {
    if (!reqInspect || !caseInspect || restored) return;

    const stored = loadStoredMapping();
    if (!stored) {
      setRestored(true);
      return;
    }

    // Restore sheet selection (validate sheets exist)
    const reqAvail = new Set(reqInspect.sheets.map(s => s.name));
    const caseAvail = new Set(caseInspect.sheets.map(s => s.name));

    if (reqAvail.has(stored.reqSheet)) {
      setReqSheet(stored.reqSheet);
    }

    const validCaseSheets = stored.caseSheets.filter(s => caseAvail.has(s));
    if (validCaseSheets.length > 0) {
      setCaseSheets(validCaseSheets);
    }

    // Restore column mappings (sanitize against available columns)
    const resolvedReqSheet = reqAvail.has(stored.reqSheet) ? stored.reqSheet : reqInspect.sheets[0]?.name ?? '';
    const reqSheetCols = reqInspect.sheets.find(s => s.name === resolvedReqSheet)?.columns ?? [];
    const reqColSet = new Set(reqSheetCols);

    const firstCaseSheetName = validCaseSheets.length > 0 ? validCaseSheets[0] : caseInspect.sheets[0]?.name ?? '';
    const caseSheetCols = caseInspect.sheets.find(s => s.name === firstCaseSheetName)?.columns ?? [];
    const caseColSet = new Set(caseSheetCols);

    setReqCols(sanitizeReqCols(stored.reqCols, reqColSet));
    setCaseCols(sanitizeCaseCols(stored.caseCols, caseColSet));
    setRestored(true);
  }, [reqInspect, caseInspect, restored]);

  // ── Inspection ──
  const handleInspect = useCallback(async () => {
    if (!reqFile || !caseFile) return;
    setError(null);
    setInspecting(true);
    try {
      const result = await inspectWorkbooks(reqFile, caseFile);
      setReqInspect(result.requirement);
      setCaseInspect(result.referenceTestCase);

      // Default sheet selection when no stored mapping applies
      if (result.requirement.sheets.length > 0) {
        setReqSheet(result.requirement.sheets[0].name);
      }
      if (result.referenceTestCase.sheets.length > 0) {
        setCaseSheets(result.referenceTestCase.sheets.map(s => s.name));
      }
      // Allow localStorage restore to process
      setRestored(false);
    } catch (e: any) {
      setError(e?.message ?? 'Failed to inspect workbooks');
    } finally {
      setInspecting(false);
    }
  }, [reqFile, caseFile]);

  // When reqSheet changes and a stored mapping was restored, keep columns in sync
  useEffect(() => {
    if (!reqInspect) return;
    const sheet = reqInspect.sheets.find(s => s.name === reqSheet);
    if (!sheet) return;
    const colSet = new Set(sheet.columns);
    setReqCols(prev => sanitizeReqCols(prev, colSet));
  }, [reqSheet, reqInspect]);

  // Toggle a case sheet selection
  function toggleCaseSheet(name: string) {
    setCaseSheets(prev =>
      prev.includes(name) ? prev.filter(s => s !== name) : [...prev, name]
    );
  }

  // ── Render ──
  return (
    <div className="prompt-learning">
      <header className="pl-header">
        <h1>Prompt Learning</h1>
      </header>
      <div className="pl-body">

        {/* ── Step 1: Upload ── */}
        <section className="pl-section">
          <h2 className="pl-section-title">1. Upload Excel Files</h2>
          <div className="pl-upload-row">
            <div className="pl-upload-group">
              <label className="pl-label">Requirement Excel (.xlsx)</label>
              <div className="pl-file-row">
                <button className="btn" onClick={() => reqInputRef.current?.click()}>
                  {reqFile ? 'Change File' : 'Choose File'}
                </button>
                <span className="pl-file-name">{reqFile ? reqFile.name : 'No file chosen'}</span>
                <input
                  ref={reqInputRef}
                  type="file"
                  accept=".xlsx"
                  hidden
                  onChange={e => setReqFile(e.target.files?.[0] ?? null)}
                />
              </div>
            </div>
            <div className="pl-upload-group">
              <label className="pl-label">Reference Test Case Excel (.xlsx)</label>
              <div className="pl-file-row">
                <button className="btn" onClick={() => caseInputRef.current?.click()}>
                  {caseFile ? 'Change File' : 'Choose File'}
                </button>
                <span className="pl-file-name">{caseFile ? caseFile.name : 'No file chosen'}</span>
                <input
                  ref={caseInputRef}
                  type="file"
                  accept=".xlsx"
                  hidden
                  onChange={e => setCaseFile(e.target.files?.[0] ?? null)}
                />
              </div>
            </div>
          </div>
          <button
            className="btn btn-primary"
            disabled={!reqFile || !caseFile || inspecting}
            onClick={handleInspect}
            style={{ marginTop: 12 }}
          >
            {inspecting ? 'Inspecting…' : 'Inspect Workbooks'}
          </button>
          {error && <div className="error-msg" style={{ marginTop: 12 }}>{error}</div>}
        </section>

        {/* ── Step 2: Sheet selection ── */}
        {reqInspect && caseInspect && (
          <section className="pl-section">
            <h2 className="pl-section-title">2. Select Sheets</h2>
            <div className="pl-sheet-selectors">
              <div className="pl-sheet-group">
                <label className="pl-label">Requirement Sheet</label>
                <select
                  className="pl-select"
                  value={reqSheet}
                  onChange={e => setReqSheet(e.target.value)}
                >
                  {reqInspect.sheets.map(s => (
                    <option key={s.name} value={s.name}>{s.name}</option>
                  ))}
                </select>
                <span className="pl-hint">
                  {reqColumns.length > 0 ? `${reqColumns.length} columns: ${reqColumns.join(', ')}` : ''}
                </span>
              </div>
              <div className="pl-sheet-group">
                <label className="pl-label">Reference Test Case Sheets</label>
                <div className="pl-checkbox-group">
                  {caseInspect.sheets.map(s => (
                    <label key={s.name} className="pl-checkbox">
                      <input
                        type="checkbox"
                        checked={caseSheets.includes(s.name)}
                        onChange={() => toggleCaseSheet(s.name)}
                      />
                      {s.name}
                    </label>
                  ))}
                </div>
                <span className="pl-hint">
                  {caseSheets.length > 0 && `Using columns from first selected sheet. Columns: ${caseColumns.join(', ')}`}
                </span>
              </div>
            </div>
          </section>
        )}

        {/* ── Step 3: Column mapping ── */}
        {reqInspect && caseInspect && reqSheet && caseSheets.length > 0 && (
          <section className="pl-section">
            <h2 className="pl-section-title">3. Map Columns</h2>
            <div className="pl-mapping-grid">
              <div className="pl-mapping-group">
                <h3 className="pl-mapping-heading">Requirement Columns</h3>
                {renderColSelect('Requirement Key', reqCols.requirementKey, reqColumns, v => setReqCols(p => ({ ...p, requirementKey: v })))}
                {renderColSelect('Description', reqCols.description, reqColumns, v => setReqCols(p => ({ ...p, description: v })))}
                {renderColSelect('Function Name', reqCols.functionName ?? '', reqColumns, v => setReqCols(p => ({ ...p, functionName: v || undefined })), true)}
                {renderColSelect('Requirement Type', reqCols.requirementType ?? '', reqColumns, v => setReqCols(p => ({ ...p, requirementType: v || undefined })), true)}
              </div>
              <div className="pl-mapping-group">
                <h3 className="pl-mapping-heading">Reference Test Case Columns</h3>
                {renderColSelect('Case ID', caseCols.caseId ?? '', caseColumns, v => setCaseCols(p => ({ ...p, caseId: v || undefined })), true)}
                {renderColSelect('Linked Requirements', caseCols.linkedRequirements, caseColumns, v => setCaseCols(p => ({ ...p, linkedRequirements: v })))}
                {renderColSelect('Title', caseCols.title, caseColumns, v => setCaseCols(p => ({ ...p, title: v })))}
                {renderColSelect('Action', caseCols.action, caseColumns, v => setCaseCols(p => ({ ...p, action: v })))}
                {renderColSelect('Expected Result', caseCols.expectedResult, caseColumns, v => setCaseCols(p => ({ ...p, expectedResult: v })))}
                {renderColSelect('Objective', caseCols.objective ?? '', caseColumns, v => setCaseCols(p => ({ ...p, objective: v || undefined })), true)}
              </div>
            </div>
            <span className="pl-hint">* Required columns. Unmapped optional columns are omitted from parsing.</span>
          </section>
        )}
      </div>
    </div>
  );
}

function renderColSelect(
  label: string,
  value: string,
  columns: string[],
  onChange: (v: string) => void,
  optional = false,
) {
  return (
    <div className="mf" style={{ marginBottom: 8 }}>
      <label>{label}{!optional ? ' *' : ''}</label>
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
      >
        <option value="">-- Select column --</option>
        {columns.map(c => (
          <option key={c} value={c}>{c}</option>
        ))}
      </select>
    </div>
  );
}
