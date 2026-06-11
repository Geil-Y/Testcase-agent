import { apiUploadForm } from './client';
import type { WorkbookInspection, RequirementColMap, RefTestCaseColMap, DataIssue, ParsedSummary } from './pl-types';

export interface InspectWorkbooksResponse {
  requirement: WorkbookInspection;
  referenceTestCase: WorkbookInspection;
}

export interface ParseAndResolveResponse {
  summary: ParsedSummary;
  dataIssues: DataIssue[];
  resolvedLinkCount: number;
  styleOnlyCaseCount: number;
  noTestRequirementCount: number;
}

/** Upload two Excel workbooks and get back sheet/column inspection. */
export async function inspectWorkbooks(
  reqFile: File,
  caseFile: File,
): Promise<InspectWorkbooksResponse> {
  const formData = new FormData();
  formData.append('req_file', reqFile);
  formData.append('case_file', caseFile);
  const result = await apiUploadForm('/pl/inspect-workbooks', formData);
  return result as InspectWorkbooksResponse;
}

/** Parse both workbooks with column mappings and resolve links. */
export async function parseAndResolve(
  reqFile: File,
  caseFile: File,
  reqSheet: string,
  caseSheets: string[],
  reqMapping: RequirementColMap,
  caseMapping: RefTestCaseColMap,
): Promise<ParseAndResolveResponse> {
  const formData = new FormData();
  formData.append('req_file', reqFile);
  formData.append('case_file', caseFile);
  formData.append('req_sheet', reqSheet);
  formData.append('case_sheets', JSON.stringify(caseSheets));
  formData.append('req_mapping', JSON.stringify(reqMapping));
  formData.append('case_mapping', JSON.stringify(caseMapping));
  const result = await apiUploadForm('/pl/parse-and-resolve', formData);
  return result as ParseAndResolveResponse;
}
