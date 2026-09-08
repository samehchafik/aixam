import type { KioskConfig, Runtime } from './types'

/**
 * Runtime navigateur : mode developpement (lien https) et mode Chromium
 * kiosque sur le salon. Le positionnement multi-ecran est delegue au script
 * de lancement (`--window-position`), plus fiable que window.open.
 */
export const webRuntime: Runtime = {
  name: 'web',

  async loadConfig() {
    const res = await fetch(`${import.meta.env.BASE_URL}config.json`, { cache: 'no-store' })
    if (!res.ok) throw new Error('config.json introuvable')
    return (await res.json()) as KioskConfig
  },

  async openDisplayWindow() {
    return false
  },

  async keepAwake() {
    try {
      const lock = (navigator as Navigator & { wakeLock?: { request(t: string): Promise<unknown> } })
        .wakeLock
      await lock?.request('screen')
    } catch {
      /* pas critique */
    }
  },
}
