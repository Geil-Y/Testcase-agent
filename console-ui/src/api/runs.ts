import { apiGet, apiPost, apiPut, apiDelete } from './client';
import type { RunDetail, SectionItem } from './types';

export function getRun(runId: number): Promise<RunDetail> {
  return apiGet<RunDetail>(`/runs/${runId}`);
}

export function createRun(requirementId: number, reviewRequired: string[]): Promise<RunDetail> {
  return apiPost<RunDetail>('/runs', { requirement_id: requirementId, review_required: reviewRequired });
}

export function advanceRun(runId: number): Promise<RunDetail> {
  return apiPost<RunDetail>(`/runs/${runId}/advance`);
}

export function evaluateRun(runId: number): Promise<{ summary: { total_cases: number; passed: number; failed: number; pass_rate: number }; cases: Array<{ case_id: number; title: string; passed: boolean; failed_items: string[]; warning_items: string[] }> }> {
  return apiPost(`/runs/${runId}/evaluate`);
}

export function updateItem(runId: number, section: string, itemId: string, changes: Partial<SectionItem>): Promise<SectionItem> {
  return apiPut<SectionItem>(`/runs/${runId}/sections/${section}/items/${itemId}`, changes);
}

export function addItem(runId: number, section: string, item: Partial<SectionItem> & { item_id: string }): Promise<SectionItem> {
  return apiPost<SectionItem>(`/runs/${runId}/sections/${section}/items`, item);
}

export function deleteItem(runId: number, section: string, itemId: string): Promise<void> {
  return apiDelete(`/runs/${runId}/sections/${section}/items/${itemId}`);
}
