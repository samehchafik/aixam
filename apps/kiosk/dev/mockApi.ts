import { readFileSync, existsSync } from 'node:fs'
import { join, resolve } from 'node:path'
import type { Plugin } from 'vite'

/**
 * API de developpement sans docker : `npm run dev:mock`.
 * Sert le bootstrap depuis les index.json de `apps/api/media` et les medias
 * en statique. Le reste (inscription, envoi) repond OK sans rien enregistrer.
 */
export function mockApi(): Plugin {
  const media = resolve(__dirname, '../../api/media')
  const readJson = (rel: string, fallback: unknown) =>
    existsSync(join(media, rel)) ? JSON.parse(readFileSync(join(media, rel), 'utf-8')) : fallback
  // Meme mise en forme que `assets.py` : les chemins sont relatifs a /media, et
  // un element sans vignette est sa propre vignette.
  type Brut = { id: string; file: string; thumb?: string; width?: number; height?: number; label: object }
  const index = (folder: string) =>
    (readJson(`${folder}/index.json`, { items: [] }).items as Brut[]).map((it) => ({
      ...it,
      image: `${folder}/${it.file}`,
      thumb: `${folder}/${it.thumb ?? it.file}`,
      width: it.width ?? 1,
      height: it.height ?? 1,
    }))

  return {
    name: 'aixam-mock-api',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = req.url ?? ''
        const json = (body: unknown, status = 200) => {
          res.statusCode = status
          res.setHeader('Content-Type', 'application/json')
          res.end(JSON.stringify(body))
        }

        // Meme origine : apiBaseUrl vide, le front tape sur ce serveur Vite.
        if (url.split('?')[0] === '/config.json') {
          return json({ apiBaseUrl: '', kioskToken: 'mock', displayMonitorIndex: 1, touchMonitorIndex: 0, idleTimeoutSeconds: 600, locale: 'fr', demoMode: true })
        }
        if (url.startsWith('/api/kiosk/bootstrap')) {
          return json({
            kiosk: { id: 'mock', name: 'Borne mock' },
            catalog: {
              shape: readJson('base/shape.json', {
                width: 3218,
                height: 325,
                points: [[0, 0], [3218, 0], [3218, 325], [0, 325]],
                notch: { x: 1330, y: 142, width: 557, height: 180 },
              }),
              backgrounds: index('backgrounds'),
              objects: index('objects'),
            },
            settings: { verification_bypass: true, idle_timeout_seconds: 600, attract_interval_seconds: 6 },
          })
        }
        if (url.startsWith('/api/kiosk/register')) return json({ visitor_id: '00000000-0000-0000-0000-000000000000', verification_required: false })
        if (url.startsWith('/api/kiosk/verify')) return json({ verified: true, remaining_attempts: 5 })
        if (url.startsWith('/api/kiosk/designs')) return json({ id: 'mock', status: 'rendered', render_url: null })
        if (url.startsWith('/api/kiosk/events')) return json(null, 204)

        if (url.startsWith('/media/')) {
          const file = join(media, decodeURIComponent(url.slice('/media/'.length).split('?')[0]))
          if (file.startsWith(media) && existsSync(file)) {
            const types: Record<string, string> = {
              svg: 'image/svg+xml',
              png: 'image/png',
              jpg: 'image/jpeg',
              jpeg: 'image/jpeg',
              webp: 'image/webp',
              json: 'application/json',
            }
            const ext = (file.split('.').pop() ?? '').toLowerCase()
            res.setHeader('Content-Type', types[ext] ?? 'application/octet-stream')
            res.end(readFileSync(file))
            return
          }
        }
        next()
      })
    },
  }
}
