import { apiGet, apiUpload } from './client';
import type { RequirementListResponse, Requirement } from './types';

export function listRequirements(params: {
  q?: string; status?: string; offset?: number; limit?: number;
} = {}): Promise<RequirementListResponse> {
  const p: Record<string, string> = {};
  if (params.q) p.q = params.q;
  if (params.status) p.status = params.status;
  if (params.offset !== undefined) p.offset = String(params.offset);
  if (params.limit !== undefined) p.limit = String(params.limit);
  return apiGet<RequirementListResponse>('/requirements', p);
}

export function getRequirement(id: number): Promise<{
  requirement: Requirement;
  runs: Array<{ id: number; status: string; review_llm_a: number; review_llm_b: number; review_llm_c: number; created_at: string }>;
}> {
  return apiGet(`/requirements/${id}`);
}

export function importRequirements(file: File, sheetName?: string): Promise<{ imported: number; total_rows: number }> {
  return apiUpload('/requirements/import', file, sheetName);
}
