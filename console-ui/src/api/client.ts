const BASE_URL = import.meta.env.VITE_API_BASE || '/api/v1/console';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (res.status === 204) return undefined as T;
  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

export function apiGet<T>(path: string, params?: Record<string, string>): Promise<T> {
  const qs = params ? '?' + new URLSearchParams(params).toString() : '';
  return request<T>(`${path}${qs}`);
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    body: body ? JSON.stringify(body) : undefined,
  });
}

export function apiPut<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: 'PUT',
    body: body ? JSON.stringify(body) : undefined,
  });
}

export function apiDelete(path: string): Promise<void> {
  return request<void>(path, { method: 'DELETE' });
}

export async function apiUpload<T>(path: string, file: File, sheetName?: string): Promise<T> {
  const formData = new FormData();
  formData.append('file', file);
  if (sheetName) formData.append('sheet_name', sheetName);
  const res = await fetch(`${BASE_URL}${path}`, { method: 'POST', body: formData });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || `${res.status}`);
  }
  return res.json();
}

export async function apiUploadForm<T>(path: string, formData: FormData): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, { method: 'POST', body: formData });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || `${res.status}`);
  }
  return res.json();
}
