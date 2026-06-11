import { useState, useEffect, useRef, useCallback } from 'react';
import { inspectWorkbooks, parseAndResolve, listVersions, readVersion, runPromptLearning } from '../api/pl-api';
import type { WorkbookInspection, RequirementColMap, RefTestCaseColMap, LearnedPromptSetListItem, LearnedPromptSetVersion } from '../api/pl-types';
import type { ParseAndResolveResponse } from '../api/pl-api';

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

  // ── Parse & resolve state ──
  const [parsing, setParsing] = useState(false);
  const [parseResult, setParseResult] = useState<ParseAndResolveResponse | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [showIssues, setShowIssues] = useState(false);

  // ── Run state ──
  const [running, setRunning] = useState(false);
  const [runStage, setRunStage] = useState('');
  const [runError, setRunError] = useState<string | null>(null);

  // ── Version history state ──
  const [versions, setVersions] = useState<LearnedPromptSetListItem[]>([]);
  const [selectedVersion, setSelectedVersion] = useState<LearnedPromptSetVersion | null>(null);
  const [versionsLoading, setVersionsLoading] = useState(false);

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

  // ── Parse & Resolve ──
  const handleParseResolve = useCallback(async () => {
    if (!reqFile || !caseFile) return;
    setParseError(null);
    setParsing(true);
    try {
      const result = await parseAndResolve(
        reqFile, caseFile, reqSheet, caseSheets, reqCols, caseCols,
      );
      setParseResult(result);
    } catch (e: any) {
      setParseError(e?.message ?? 'Parse failed');
    } finally {
      setParsing(false);
    }
  }, [reqFile, caseFile, reqSheet, caseSheets, reqCols, caseCols]);

  // When reqSheet changes and a stored mapping was restored, keep columns in sync
  useEffect(() => {
    if (!reqInspect) return;
    const sheet = reqInspect.sheets.find(s => s.name === reqSheet);
    if (!sheet) return;
    const colSet = new Set(sheet.columns);
    setReqCols(prev => sanitizeReqCols(prev, colSet));
  }, [reqSheet, reqInspect]);

  // ── Run Prompt Learning ──
  async function doReloadVersions() {
    try {
      const result = await listVersions();
      setVersions(result.versions);
    } catch { /* silent */ }
  }

  const handleRun = useCallback(async () => {
    if (!reqFile || !caseFile) return;
    setRunError(null);
    setRunning(true);
    try {
      setRunStage('Running Prompt Learning…');
      const result = await runPromptLearning(
        reqFile, caseFile, reqSheet, caseSheets, reqCols, caseCols, undefined,
      );
      setRunStage('Saving…');
      // Refresh version list
      await doReloadVersions();
      // Open the new version's rationale
      const v = await readVersion(result.version);
      setSelectedVersion(v);
      setRunStage('');
    } catch (e: any) {
      setRunError(e?.message ?? 'Run failed');
      setRunStage('');
    } finally {
      setRunning(false);
    }
  }, [reqFile, caseFile, reqSheet, caseSheets, reqCols, caseCols]);

  // ── Load version history on mount ──
  useEffect(() => {
    let cancelled = false;
    async function load() {
      setVersionsLoading(true);
      try {
        const result = await listVersions();
        if (!cancelled) setVersions(result.versions);
      } catch {
        // silent — version list is optional
      } finally {
        if (!cancelled) setVersionsLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  // ── Select a version to view ──
  async function handleSelectVersion(version: string) {
    try {
      const v = await readVersion(version);
      setSelectedVersion(v);
    } catch {
      // silent
    }
  }

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

        {/* ── Step 4: Parse & Resolve ── */}
        {reqInspect && caseInspect && reqSheet && caseSheets.length > 0 && (
          <section className="pl-section">
            <h2 className="pl-section-title">4. Parse &amp; Resolve</h2>
            <button
              className="btn btn-primary"
              disabled={parsing}
              onClick={handleParseResolve}
            >
              {parsing ? 'Parsing…' : 'Parse & Resolve Links'}
            </button>
            {parseError && <div className="error-msg" style={{ marginTop: 12 }}>{parseError}</div>}

            {/* ── Summary display ── */}
            {parseResult && (
              <div className="pl-summary" style={{ marginTop: 16 }}>
                <div className="pl-summary-grid">
                  <SummaryCard label="Requirements" value={parseResult.summary.requirementCount} />
                  <SummaryCard label="Reference Cases" value={parseResult.summary.refTestCaseCount} />
                  <SummaryCard label="Valid Links" value={parseResult.summary.validLinkCount} />
                  <SummaryCard label="No-Test" value={parseResult.summary.noTestRequirementCount} />
                  <SummaryCard label="Style-Only Cases" value={parseResult.summary.styleOnlyCaseCount} />
                  <SummaryCard label="Data Issues" value={parseResult.summary.dataIssueCount} accent={parseResult.summary.dataIssueCount > 0} />
                </div>

                {/* ── Data issue details ── */}
                {parseResult.dataIssues.length > 0 && (
                  <div style={{ marginTop: 12 }}>
                    <button
                      className="btn btn-sm"
                      onClick={() => setShowIssues(!showIssues)}
                    >
                      {showIssues ? 'Hide' : 'Show'} Data Issues ({parseResult.dataIssues.length})
                    </button>
                    {showIssues && (
                      <div className="pl-issues-list" style={{ marginTop: 8 }}>
                        {parseResult.dataIssues.map((issue, i) => (
                          <div key={i} className="pl-issue-item">
                            <span className="pl-issue-type">{issue.issueType}</span>
                            <span className="pl-issue-loc">
                              {issue.fileType} / {issue.sheet}{issue.row != null ? ` row ${issue.row}` : ''}
                            </span>
                            <span className="pl-issue-msg">{issue.message}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </section>
        )}

        {/* ── Run Prompt Learning ── */}
        {reqInspect && caseInspect && reqSheet && caseSheets.length > 0 && (
          <section className="pl-section">
            <h2 className="pl-section-title">5. Run Prompt Learning</h2>
            <button
              className="btn btn-primary"
              disabled={running}
              onClick={handleRun}
            >
              {running ? (runStage || 'Running…') : 'Run Prompt Learning'}
            </button>
            {runError && <div className="error-msg" style={{ marginTop: 12 }}>{runError}</div>}
          </section>
        )}

        {/* ── Version history ── */}
        <section className="pl-section">
          <h2 className="pl-section-title">Learned Prompt Sets</h2>
          {versionsLoading && <span className="text-muted">Loading…</span>}
          {!versionsLoading && versions.length === 0 && (
            <span className="text-muted">No learned prompt sets yet.</span>
          )}
          {versions.length > 0 && (
            <div className="pl-version-list">
              {versions.map(v => (
                <div
                  key={v.version}
                  className={`pl-version-item${selectedVersion?.meta.version === v.version ? ' selected' : ''}`}
                  onClick={() => handleSelectVersion(v.version)}
                >
                  <span className="pl-version-name">{v.version}</span>
                  <span className="pl-version-date">{v.createdAt}</span>
                  <span className="pl-version-model">{v.model}</span>
                  <span className="pl-version-counts">
                    {v.summary.requirementCount} req / {v.summary.refTestCaseCount} cases
                    {v.summary.dataIssueCount > 0 && ` / ${v.summary.dataIssueCount} issues`}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* ── Version detail ── */}
          {selectedVersion && (
            <div className="pl-version-detail" style={{ marginTop: 16 }}>
              <h3 className="pl-section-title">rationale.md</h3>
              <pre className="pl-rationale">{selectedVersion.rationale}</pre>

              <h3 className="pl-section-title" style={{ marginTop: 16 }}>Prompt Files</h3>
              {selectedVersion.promptGroups.map(g => (
                <details key={g.stage} className="pl-prompt-group" open>
                  <summary className="pl-prompt-summary">
                    LLM-{g.stage}: {g.stageLabel}
                  </summary>
                  <div className="pl-prompt-panel">
                    <h4>{g.systemPrompt.filename}</h4>
                    <pre className="pl-prompt-content">{g.systemPrompt.content}</pre>
                  </div>
                  <div className="pl-prompt-panel">
                    <h4>{g.userPrompt.filename}</h4>
                    <pre className="pl-prompt-content">{g.userPrompt.content}</pre>
                  </div>
                </details>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function SummaryCard({ label, value, accent }: { label: string; value: number; accent?: boolean }) {
  return (
    <div className={`pl-summary-card${accent ? ' pl-summary-accent' : ''}`}>
      <div className="pl-summary-value">{value}</div>
      <div className="pl-summary-label">{label}</div>
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
