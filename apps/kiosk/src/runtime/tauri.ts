import type { KioskConfig, Runtime } from './types'

/**
 * Runtime Tauri. Tous les imports sont dynamiques : le bundle reste chargeable
 * dans un navigateur ordinaire, ou ce fichier n'est jamais evalue.
 *
 * C'est ici que se trouve le seul vrai avantage de Tauri sur un navigateur :
 * placer une fenetre plein ecran sur un moniteur precis, sans geste
 * utilisateur ni permission.
 */
export const tauriRuntime: Runtime = {
  name: 'tauri',

  async loadConfig() {
    const { resolveResource } = await import('@tauri-apps/api/path')
    const { readTextFile } = await import('@tauri-apps/plugin-fs')
    // config.json est livre a cote de l'executable : l'installateur du salon
    // l'edite sans recompiler.
    const path = await resolveResource('config.json')
    return JSON.parse(await readTextFile(path)) as KioskConfig
  },

  async openDisplayWindow(config: KioskConfig) {
    const { availableMonitors } = await import('@tauri-apps/api/window')
    const { WebviewWindow } = await import('@tauri-apps/api/webviewWindow')

    if (await WebviewWindow.getByLabel('display')) return true

    const monitors = await availableMonitors()
    const monitor = monitors[config.displayMonitorIndex] ?? monitors[monitors.length - 1]
    if (!monitor) return false

    const win = new WebviewWindow('display', {
      url: 'index.html#/display',
      x: monitor.position.x,
      y: monitor.position.y,
      width: monitor.size.width,
      height: monitor.size.height,
      decorations: false,
      fullscreen: true,
      alwaysOnTop: false,
      title: 'AIXAM EASY',
    })
    await new Promise<void>((resolve) => {
      win.once('tauri://created', () => resolve())
      win.once('tauri://error', () => resolve())
    })
    return true
  },

  async keepAwake() {
    /* gere cote Rust via le plugin tauri-plugin-prevent-default / OS settings */
  },
}
