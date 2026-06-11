import { apiUploadForm } from './client';
import type { WorkbookInspection } from './pl-types';

export interface InspectWorkbooksResponse {
  requirement: WorkbookInspection;
  referenceTestCase: WorkbookInspection;
}

/** Upload two Excel workbooks and get back sheet/column inspection. */
export async function inspectWorkbooks(
  reqFile: File,
  caseFile: File,
): Promise<InspectWorkbooksResponse> {
  const formData = new FormData();
  formData.append('req_file', reqFile);
  formData.append('case_file', caseFile);
  // apiUpload posts FormData and returns parsed JSON
  const result = await apiUploadForm('/pl/inspect-workbooks', formData);
  return result as InspectWorkbooksResponse;
}
