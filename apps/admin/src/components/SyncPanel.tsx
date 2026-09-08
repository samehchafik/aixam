import { useEffect, useState } from 'react'
import { api } from '../lib/api'

type SyncCfg = {
  url: string
  token_set: boolean
  server_enabled: boolean
  local: { visitors: number; designs: number; events: number }
  cursors: Record<string, string | null>
  last_push_at: string | null
}

const dateFr = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString('fr-FR') : 'jamais'

/** Remontee des donnees du stand vers le serveur. Sens unique. */
export function SyncPanel() {
  const [cfg, setCfg] = useState<SyncCfg | null>(null)
  const [token, setToken] = useState('')
  const [saved, setSaved] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const load = () => api<SyncCfg>('/api/admin/sync').then(setCfg)
  useEffect(() => {
    load()
  }, [])

  if (!cfg) return <p className="muted">Chargement...</p>

  const save = async () => {
    setCfg(
      await api<SyncCfg>('/api/admin/sync', {
        method: 'PUT',
        body: JSON.stringify({ url: cfg.url, ...(token ? { token } : {}) }),
      }),
    )
    setToken('')
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  const test = async () => {
    setMessage('Test en cours...')
    const r = await api<{ ok: boolean; error?: string; remote?: Record<string, number | string> }>(
      '/api/admin/sync/test',
      { method: 'POST' },
    )
    setMessage(
      r.ok
        ? `Liaison etablie — enregistre sous « ${r.remote!.client} ». Le serveur detient ${r.remote!.visitors} visiteur(s) et ${r.remote!.designs} creation(s).`
        : `Echec : ${r.error}`,
    )
  }

  const push = async (full: boolean) => {
    if (full && !confirm(
      "Tout renvoyer reexpedie l'integralite des donnees. Sans danger (rien n'est duplique), " +
      "mais un visiteur efface cote serveur y reapparaitra. Continuer ?")) return
    setBusy(true)
    setMessage(full ? 'Renvoi complet en cours...' : 'Envoi en cours...')
    try {
      const r = await api<{ ok: boolean; error?: string; totaux?: Record<string, number> }>(
        `/api/admin/sync/push${full ? '?full=true' : ''}`,
        { method: 'POST' },
      )
      setMessage(
        r.ok
          ? `Termine : ${r.totaux!.visitors} visiteur(s), ${r.totaux!.designs} creation(s), ${r.totaux!.events} evenement(s) envoyes.`
          : `Echec : ${r.error}`,
      )
      load()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="settings">
      <p className="muted hint">
        Le stand produit, le serveur consolide. L'envoi ne part que dans ce sens, et
        renvoyer deux fois ne cree pas de doublon : chaque ligne garde son identifiant.
      </p>

      <label>
        <span>Adresse du back-office serveur</span>
        <input
          type="text"
          placeholder="https://aixam-admin.ifrit.fr"
          value={cfg.url}
          onChange={(e) => setCfg({ ...cfg, url: e.target.value })}
        />
      </label>

      <label>
        <span>Jeton</span>
        <input
          type="password"
          autoComplete="off"
          placeholder={cfg.token_set ? 'Jeton en place — laisser vide pour le garder' : 'axr_...'}
          value={token}
          onChange={(e) => setToken(e.target.value)}
        />
        <p className="muted hint">
          Le meme que pour le relais d'emails : genere dans « Clients de relais » du
          back-office serveur.
        </p>
      </label>

      <div className="toolbar">
        <button onClick={save}>{saved ? 'Enregistre' : 'Enregistrer'}</button>
        <button className="link" onClick={test}>Tester la liaison</button>
      </div>

      <table>
        <thead><tr><th /><th>En local</th><th>Envoye jusqu'au</th></tr></thead>
        <tbody>
          <tr><td>Visiteurs</td><td>{cfg.local.visitors}</td><td className="muted">{dateFr(cfg.cursors.visitors)}</td></tr>
          <tr><td>Creations</td><td>{cfg.local.designs}</td><td className="muted">{dateFr(cfg.cursors.designs)}</td></tr>
          <tr><td>Evenements</td><td>{cfg.local.events}</td><td className="muted">{dateFr(cfg.cursors.events)}</td></tr>
        </tbody>
      </table>

      <div className="toolbar">
        <button disabled={busy} onClick={() => push(false)}>Envoyer les nouveautes</button>
        <button className="link" disabled={busy} onClick={() => push(true)}>Tout renvoyer</button>
      </div>
      <p className="muted hint">Dernier envoi : {dateFr(cfg.last_push_at)}</p>
      {message && <p className="muted hint">{message}</p>}
    </div>
  )
}
