// ── Typed Console API client ─────────────────────────────────────────────

const BASE = '/api/v1/console'

class ApiError extends Error {
  status: number
  body: unknown

  constructor(status: number, body: unknown) {
    const msg = typeof body === 'object' && body !== null && 'error' in body
      ? String((body as Record<string, unknown>).error)
      : `API error ${status}`
    super(msg)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { ...(init?.headers as Record<string, string> || {}) }
  if (!(init?.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
  }
  const res = await fetch(`${BASE}${path}`, { ...init, headers })
  const body = await res.json().catch(() => null)
  if (!res.ok) {
    throw new ApiError(res.status, body)
  }
  return body as T
}

function get<T>(path: string): Promise<T> {
  return request<T>(path)
}

function post<T>(path: string, data?: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    body: data ? JSON.stringify(data) : undefined,
  })
}

function upload<T>(path: string, formData: FormData): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    body: formData,
  })
}

// ── Exports ───────────────────────────────────────────────────────────────

export { ApiError, get, post, upload, BASE }
