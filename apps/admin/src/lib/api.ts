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

/**
 * `detail` est une chaine pour un refus metier, un TABLEAU d'objets pour une
 * erreur de validation (422) : sans ce tri, le message affiche serait
 * « [object Object] ».
 */
function messageDErreur(corps: unknown, status: number): string {
  const detail = (corps as { detail?: unknown })?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const messages = detail
      .map((d) => (d && typeof (d as { msg?: unknown }).msg === 'string' ? (d as { msg: string }).msg : null))
      .filter((m): m is string => Boolean(m))
    if (messages.length) return messages.join(' — ')
  }
  return `HTTP ${status}`
}

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
    throw new Error(messageDErreur(await res.json().catch(() => ({})), res.status))
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
