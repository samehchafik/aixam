import { useEffect, useState } from 'react'
import { api } from '../lib/api'

export type MailCfg = {
  transport: 'smtp' | 'brevo' | 'relay'
  transports: string[]
  mail_from: string
  mail_from_name: string
  smtp_host: string
  smtp_port: number
  smtp_configured: boolean
  brevo_configured: boolean
  relay_url: string
  relay_token_set: boolean
  relay_server_enabled: boolean
  relay_default_daily_quota: number
}

const EXPLAIN: Record<MailCfg['transport'], string> = {
  smtp: "La boite du serveur OVH, ou le relais SMTP de Brevo. Demande que le port SMTP sorte du reseau.",
  brevo: "L'API HTTP de Brevo. Tout passe en 443 : a choisir si le reseau du salon filtre le port 587.",
  relay: "On n'expedie pas d'ici. Les emails sont confies a un autre back-office AIXAM, qui a la configuration d'envoi et la reputation aupres des messageries.",
}

/** Par ou sortent les emails de CE back-office. */
export function MailConfig({ onLoaded }: { onLoaded?: (cfg: MailCfg) => void }) {
  const [cfg, setCfg] = useState<MailCfg | null>(null)
  const [token, setToken] = useState('')
  const [saved, setSaved] = useState(false)
  const [probe, setProbe] = useState<string | null>(null)
  const [testTo, setTestTo] = useState('')
  const [testMsg, setTestMsg] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = () =>
    api<MailCfg>('/api/admin/mail').then((next) => {
      setCfg(next)
      onLoaded?.(next)
    })

  useEffect(() => {
    load()
  }, [])

  if (!cfg) return <p className="muted">Chargement...</p>

  const save = async () => {
    setError(null)
    try {
      const next = await api<MailCfg>('/api/admin/mail', {
        method: 'PUT',
        body: JSON.stringify({
          transport: cfg.transport,
          relay_url: cfg.relay_url,
          // Champ vide = « ne touche pas » : le token n'est jamais reaffiche,
          // le laisser vide ne doit pas l'effacer.
          ...(token ? { relay_token: token } : {}),
        }),
      })
      setCfg(next)
      setToken('')
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const testRelay = async () => {
    setProbe('Test en cours...')
    const res = await api<{ ok: boolean; error?: string; remote?: Record<string, unknown> }>(
      '/api/admin/mail/test-relay',
      { method: 'POST' },
    )
    setProbe(
      res.ok
        ? `Liaison etablie — enregistre sous « ${res.remote!.client} », expedie depuis ${res.remote!.mail_from}, ${res.remote!.remaining_today} envoi(s) restant(s) aujourd'hui.`
        : `Echec : ${res.error}`,
    )
  }

  const sendTest = async () => {
    setTestMsg(null)
    try {
      await api('/api/admin/mail/test-send', {
        method: 'POST',
        body: JSON.stringify({ to: testTo }),
      })
      setTestMsg(`Email de test mis en file pour ${testTo}. Suivez-le dans « Emails ».`)
      setTestTo('')
    } catch (e) {
      setTestMsg(`Echec : ${(e as Error).message}`)
    }
  }

  const misconfigured =
    (cfg.transport === 'smtp' && !cfg.smtp_configured) ||
    (cfg.transport === 'brevo' && !cfg.brevo_configured) ||
    (cfg.transport === 'relay' && (!cfg.relay_url || !cfg.relay_token_set))

  return (
    <div className="settings">
      <label>
        <span>Par ou sortent les emails</span>
        <select
          value={cfg.transport}
          onChange={(e) => setCfg({ ...cfg, transport: e.target.value as MailCfg['transport'] })}
        >
          <option value="smtp">SMTP — boite OVH ou relais Brevo</option>
          <option value="brevo">Brevo — API HTTP</option>
          <option value="relay">Relais — via un autre back-office AIXAM</option>
        </select>
        <p className="muted hint">{EXPLAIN[cfg.transport]}</p>
      </label>

      {cfg.transport === 'smtp' && (
        <p className="muted hint">
          {cfg.smtp_configured
            ? `Serveur : ${cfg.smtp_host}:${cfg.smtp_port} — expediteur ${cfg.mail_from}`
            : 'SMTP_HOST n’est pas renseigne dans le .env : aucun email ne partira.'}
        </p>
      )}

      {cfg.transport === 'brevo' && (
        <p className="muted hint">
          {cfg.brevo_configured
            ? `Cle API en place — expediteur ${cfg.mail_from}`
            : 'BREVO_API_KEY n’est pas renseignee dans le .env : aucun email ne partira.'}
        </p>
      )}

      {cfg.transport === 'relay' && (
        <>
          <label>
            <span>Adresse du back-office distant</span>
            <input
              type="text"
              placeholder="https://bo.aixam.fr"
              value={cfg.relay_url}
              onChange={(e) => setCfg({ ...cfg, relay_url: e.target.value })}
            />
            <p className="muted hint">
              En https : le token voyagerait en clair sur le reseau du salon autrement.
            </p>
          </label>

          <label>
            <span>Token de relais</span>
            <input
              type="password"
              autoComplete="off"
              placeholder={cfg.relay_token_set ? 'Token en place — laisser vide pour le garder' : 'axr_...'}
              value={token}
              onChange={(e) => setToken(e.target.value)}
            />
            <p className="muted hint">
              Genere dans « Clients de relais » du back-office distant. Il n'y est affiche
              qu'une fois, a sa creation.
            </p>
          </label>
        </>
      )}

      {misconfigured && (
        <p className="warn">
          Configuration incomplete : les emails s'empileront dans la file sans partir.
        </p>
      )}
      {error && <p className="error">{error}</p>}

      <div className="toolbar">
        <button onClick={save}>{saved ? 'Enregistre' : 'Enregistrer'}</button>
        {cfg.transport === 'relay' && (
          <button className="link" onClick={testRelay}>
            Tester la liaison
          </button>
        )}
      </div>
      {probe && <p className="muted hint">{probe}</p>}

      <label>
        <span>Envoyer un email de test</span>
        <div className="toolbar">
          <input
            type="email"
            placeholder="vous@exemple.fr"
            value={testTo}
            onChange={(e) => setTestTo(e.target.value)}
          />
          <button className="link" disabled={!testTo} onClick={sendTest}>
            Envoyer
          </button>
        </div>
        <p className="muted hint">
          Passe par la file et le worker : c'est la chaine complete qui est validee, pas
          seulement la configuration.
        </p>
      </label>
      {testMsg && <p className="muted hint">{testMsg}</p>}
    </div>
  )
}
