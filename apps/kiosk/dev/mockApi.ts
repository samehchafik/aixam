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
  const index = (folder: string) =>
    (readJson(`${folder}/index.json`, { items: [] }).items as { id: string; file: string; label: object }[]).map(
      (it) => ({ ...it, image: `${folder}/${it.file}` }),
    )

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
              shape: readJson('base/shape.json', { width: 3000, height: 300, cornerRadius: 95, notch: { width: 510, height: 170, radius: 34 } }),
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
            const ext = file.split('.').pop()
            res.setHeader('Content-Type', ext === 'png' ? 'image/png' : ext === 'json' ? 'application/json' : 'image/jpeg')
            res.end(readFileSync(file))
            return
          }
        }
        next()
      })
    },
  }
}
