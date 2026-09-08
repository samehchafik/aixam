const TOKEN_KEY = 'aixam.admin.token'

export const auth = {
  get token() {
    return localStorage.getItem(TOKEN_KEY)
  },
  set(token: string) {
    localStorage.setItem(TOKEN_KEY, token)
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY)
  },
}

export class Unauthorized extends Error {}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(auth.token ? { Authorization: `Bearer ${auth.token}` } : {}),
      ...(init.headers ?? {}),
    },
  })
  if (res.status === 401) {
    auth.clear()
    throw new Unauthorized('Session expiree')
  }
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new Error(detail.detail ?? `HTTP ${res.status}`)
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T)
}

export type Stats = {
  visitors_total: number
  visitors_verified: number
  designs_total: number
  designs_rendered: number
  emails_pending: number
  emails_failed: number
}
