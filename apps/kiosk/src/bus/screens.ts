import type { KioskConfig, ScreenRole } from '../runtime'

export type BusMessage =
  | { type: 'state'; step: string; layers: unknown[]; firstName?: string }
  | { type: 'idle' }
  | { type: 'finished'; renderUrl: string | null }

type Handler = (message: BusMessage) => void

/**
 * Canal entre l'ecran tactile et le grand ecran.
 *
 * Un seul mecanisme (WebSocket via l'API) plutot que BroadcastChannel : ca
 * marche a l'identique en local sur la borne, entre deux fenetres Tauri, et a
 * distance pendant le developpement. Reconnexion automatique, car un cable
 * reseau se debranche toujours au pire moment sur un salon.
 */
export class ScreenBus {
  private socket: WebSocket | null = null
  private handlers = new Set<Handler>()
  private closed = false
  private retry = 0
  private queue: BusMessage[] = []

  constructor(
    private config: KioskConfig,
    private role: ScreenRole,
  ) {}

  connect() {
    if (this.closed) return
    const base = (this.config.apiBaseUrl || window.location.origin).replace(/^http/, 'ws')
    const url = `${base}/ws/screens?token=${encodeURIComponent(this.config.kioskToken)}&role=${this.role}`
    const socket = new WebSocket(url)
    this.socket = socket

    socket.onopen = () => {
      this.retry = 0
      this.queue.splice(0).forEach((message) => socket.send(JSON.stringify(message)))
    }
    socket.onmessage = (event) => {
      const message = JSON.parse(event.data) as BusMessage
      this.handlers.forEach((handler) => handler(message))
    }
    socket.onclose = () => {
      if (this.closed) return
      this.retry = Math.min(this.retry + 1, 6)
      setTimeout(() => this.connect(), 250 * 2 ** this.retry)
    }
    socket.onerror = () => socket.close()
  }

  send(message: BusMessage) {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(message))
    } else {
      // On ne garde que le dernier etat : rejouer l'historique n'a aucun sens.
      this.queue = this.queue.filter((m) => m.type !== message.type)
      this.queue.push(message)
    }
  }

  on(handler: Handler) {
    this.handlers.add(handler)
    return () => this.handlers.delete(handler)
  }

  close() {
    this.closed = true
    this.socket?.close()
  }
}
