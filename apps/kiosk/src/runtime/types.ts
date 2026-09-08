export type KioskConfig = {
  /** Host des appels REST. C'est LE reglage a changer a l'installation. */
  apiBaseUrl: string
  kioskToken: string
  /** Index du moniteur (0-based) pour chaque ecran, en mode application native. */
  displayMonitorIndex: number
  touchMonitorIndex: number
  idleTimeoutSeconds: number
  locale: string
  /** Mode demo : bouton « Je passe » sur le formulaire pour aller droit a l'editeur. */
  demoMode?: boolean
}

export type ScreenRole = 'touch' | 'display'

export interface Runtime {
  readonly name: 'web' | 'tauri'
  loadConfig(): Promise<KioskConfig>
  /**
   * Ouvre le second ecran en plein ecran sur le moniteur voulu.
   * Retourne false si le runtime ne sait pas le faire tout seul -- dans ce cas
   * c'est le script de lancement (Chromium kiosque) qui s'en charge.
   */
  openDisplayWindow(config: KioskConfig): Promise<boolean>
  /** Empeche la mise en veille pendant les 10 jours du salon. */
  keepAwake(): Promise<void>
}
