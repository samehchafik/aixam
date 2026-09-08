import type { Runtime } from './types'
import { webRuntime } from './web'

export * from './types'

const isTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window

let cached: Runtime | null = null

/**
 * Point unique de dependance a la plateforme. Le reste de l'application
 * n'importe jamais `@tauri-apps/*` : basculer vers Electron ou vers un simple
 * Chromium kiosque ne touche que ce dossier.
 */
export async function getRuntime(): Promise<Runtime> {
  if (cached) return cached
  cached = isTauri ? (await import('./tauri')).tauriRuntime : webRuntime
  return cached
}
