import type { KioskConfig } from '../runtime'
import type { SkinShape } from '../skin/shape'

/** Un calque : fond (image ou couleur unie) ou objet pose sur la planche. */
export type Layer = {
  type: 'background' | 'object'
  assetId?: string
  hex?: string
  /** Centre de l'element, en fraction de la largeur/hauteur de la planche. */
  x: number
  y: number
  /** Largeur en fraction de la largeur de la planche. Absent = fond en mode "cover". */
  scale?: number
  rotation: number
  opacity: number
  z: number
}

export type CatalogItem = {
  id: string
  file: string
  /** Chemin relatif a /media. */
  image: string
  /** Texte au survol, par langue. */
  label: Partial<Record<string, string>>
}

export type Catalog = {
  shape: SkinShape
  backgrounds: CatalogItem[]
  objects: CatalogItem[]
}

export type KioskSettings = {
  verification_bypass: boolean
  idle_timeout_seconds: number
  attract_interval_seconds: number
}

export class ApiClient {
  constructor(private config: KioskConfig) {}

  get base() {
    return this.config.apiBaseUrl
  }

  get mediaBase() {
    return `${this.config.apiBaseUrl}/media`
  }

  /** URL absolue d'un element de catalogue. */
  asset(item: CatalogItem) {
    return `${this.mediaBase}/${item.image}`
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const res = await fetch(`${this.config.apiBaseUrl}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        'X-Kiosk-Token': this.config.kioskToken,
        ...(init.headers ?? {}),
      },
    })
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}))
      throw new Error(detail.detail ?? `HTTP ${res.status}`)
    }
    return res.status === 204 ? (undefined as T) : ((await res.json()) as T)
  }

  bootstrap() {
    return this.request<{
      kiosk: { id: string; name: string }
      catalog: Catalog
      settings: KioskSettings
    }>('/api/kiosk/bootstrap')
  }

  register(body: {
    first_name: string
    last_name: string
    email: string
    postal_code: string
    consent_marketing: boolean
    session_id: string
  }) {
    return this.request<{ visitor_id: string; verification_required: boolean }>(
      '/api/kiosk/register',
      { method: 'POST', body: JSON.stringify(body) },
    )
  }

  verify(visitor_id: string, code: string) {
    return this.request<{ verified: boolean; remaining_attempts: number }>('/api/kiosk/verify', {
      method: 'POST',
      body: JSON.stringify({ visitor_id, code }),
    })
  }

  saveDesign(body: { session_id: string; visitor_id: string | null; layers: Layer[] }) {
    return this.request<{ id: string; status: string; render_url: string | null }>(
      '/api/kiosk/designs',
      { method: 'POST', body: JSON.stringify(body) },
    )
  }

  /** Journalise une action. Volontairement "fire and forget". */
  track(name: string, payload: Record<string, unknown> = {}, session_id?: string) {
    void this.request<void>('/api/kiosk/events', {
      method: 'POST',
      body: JSON.stringify({ name, payload, session_id: session_id ?? null }),
    }).catch(() => {})
  }
}
