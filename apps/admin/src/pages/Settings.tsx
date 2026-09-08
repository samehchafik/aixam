import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { MailConfig, type MailCfg } from '../components/MailConfig'
import { RelayClients } from '../components/RelayClients'
import { SyncPanel } from '../components/SyncPanel'

type Config = {
  verification_bypass: boolean
  idle_timeout_seconds: number
  attract_interval_seconds: number
}

export function Settings() {
  const [config, setConfig] = useState<Config | null>(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    api<Config>('/api/admin/settings').then(setConfig)
  }, [])

  const save = async () => {
    if (!config) return
    setConfig(await api<Config>('/api/admin/settings', {
      method: 'PUT',
      body: JSON.stringify(config),
    }))
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  const [kiosks, setKiosks] = useState<{ id: string; name: string; token: string }[]>([])
  useEffect(() => {
    api<typeof kiosks>('/api/admin/kiosks').then(setKiosks)
  }, [])

  // La section « Clients de relais » n'a de sens que sur le back-office qui a
  // accepte ce role (RELAY_SERVER_ENABLED) ; ailleurs elle serait un ecran mort.
  const [mail, setMail] = useState<MailCfg | null>(null)

  if (!config) return <p className="muted">Chargement...</p>

  return (
    <>
      <h1>Reglages</h1>

      <div className="settings">
        <label className="switch">
          <input
            type="checkbox"
            checked={config.verification_bypass}
            onChange={(e) => setConfig({ ...config, verification_bypass: e.target.checked })}
          />
          <div>
            <strong>Mode degrade : ignorer la verification email</strong>
            <p className="muted">
              A activer si le reseau du salon tombe. Les visiteurs passent directement a la
              creation ; les emails partent quand la connexion revient.
            </p>
          </div>
        </label>

        <label>
          <span>Retour a l'accueil apres inactivite (secondes)</span>
          <input
            type="number"
            value={config.idle_timeout_seconds}
            onChange={(e) =>
              setConfig({ ...config, idle_timeout_seconds: Number(e.target.value) })
            }
          />
        </label>

        <label>
          <span>Vitesse du slideshow d'attente (secondes)</span>
          <input
            type="number"
            value={config.attract_interval_seconds}
            onChange={(e) =>
              setConfig({ ...config, attract_interval_seconds: Number(e.target.value) })
            }
          />
        </label>

        <button onClick={save}>{saved ? 'Enregistre' : 'Enregistrer'}</button>
      </div>

      <h2>Envoi des emails</h2>
      <MailConfig onLoaded={setMail} />

      <SyncPanel />

      <h2>Bornes</h2>
      <table>
        <thead><tr><th>Nom</th><th>Token (a copier dans config.json)</th></tr></thead>
        <tbody>
          {kiosks.map((k) => (
            <tr key={k.id}><td>{k.name}</td><td><code>{k.token}</code></td></tr>
          ))}
        </tbody>
      </table>

      {mail?.relay_server_enabled && (
        <>
          <h2>Clients de relais</h2>
          <RelayClients defaultQuota={mail.relay_default_daily_quota} />
        </>
      )}
    </>
  )
}
