import type { Runtime } from './types'
import { webRuntime } from './web'

export * from './types'

// Etre DANS l'application empaquetee, ce n'est pas seulement voir les objets
// de Tauri : borne.exe, qui n'est qu'un navigateur en plein ecran, les
// injecte aussi dans la page qu'il ouvre depuis http://localhost:8080. La
// borne s'y croyait empaquetee, cherchait config.json par les API Tauri, et
// s'ouvrait sur « Erreur de demarrage ». L'application empaquetee, elle, est
// servie depuis son propre hote.
const isTauri =
  typeof window !== 'undefined' &&
  '__TAURI_INTERNALS__' in window &&
  (window.location.protocol === 'tauri:' || window.location.hostname === 'tauri.localhost')

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
