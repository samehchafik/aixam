const TOKEN_KEY = 'aixam.admin.token'

/**
 * La session, et qui la surveille.
 *
 * Effacer le jeton ne suffisait pas : l'ecran restait sur le tableau de bord,
 * qui se vidait appel apres appel pendant que l'API repondait 401. Toute
 * disparition du jeton previent donc maintenant l'application, qui revient a
 * la page de connexion.
 */
const abonnes = new Set<() => void>()
/** Vrai quand la session s'est terminee d'elle-meme, pas sur un clic. */
let expiree = false

export const auth = {
  get token() {
    return localStorage.getItem(TOKEN_KEY)
  },
  /** Vrai si la derniere fin de session est une expiration, non une deconnexion. */
  get aExpire() {
    return expiree
  },
  set(token: string) {
    expiree = false
    localStorage.setItem(TOKEN_KEY, token)
    abonnes.forEach((prevenir) => prevenir())
  },
  clear(cause: 'deconnexion' | 'expiration' = 'deconnexion') {
    expiree = cause === 'expiration'
    localStorage.removeItem(TOKEN_KEY)
    abonnes.forEach((prevenir) => prevenir())
  },
  /** S'abonner aux changements de session. Rend la fonction de desabonnement. */
  surChangement(prevenir: () => void) {
    abonnes.add(prevenir)
    return () => {
      abonnes.delete(prevenir)
    }
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
    // Un back-office ne doit jamais montrer un etat perime : sans en-tete de
    // cache cote API, le navigateur rejoue volontiers une reponse GET, et
    // l'ecran ment apres une synchronisation ou un envoi.
    cache: 'no-store',
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(auth.token ? { Authorization: `Bearer ${auth.token}` } : {}),
      ...(init.headers ?? {}),
    },
  })
  if (res.status === 401) {
    auth.clear('expiration')
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


/**
 * Telecharge un fichier servi par l'API.
 *
 * Un simple <a href> ne peut pas porter l'en-tete Authorization : l'export CSV
 * repondait donc 401, sans que rien ne l'indique a l'ecran.
 */
export async function telecharger(path: string, nom: string): Promise<void> {
  const res = await fetch(path, {
    cache: 'no-store',
    headers: auth.token ? { Authorization: `Bearer ${auth.token}` } : {},
  })
  // Un telechargement passe hors de `api()` : sans ce test, une session
  // expiree rendait un fichier contenant le refus de l'API.
  if (res.status === 401) {
    auth.clear('expiration')
    throw new Unauthorized('Session expiree')
  }
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const url = URL.createObjectURL(await res.blob())
  const lien = document.createElement('a')
  lien.href = url
  lien.download = nom
  lien.click()
  URL.revokeObjectURL(url)
}
