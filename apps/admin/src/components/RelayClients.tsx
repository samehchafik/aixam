import { useEffect, useState } from 'react'
import { api } from '../lib/api'

type Client = {
  id: string
  name: string
  token_prefix: string
  is_active: boolean
  daily_quota: number
  sent_today: number
  sent_total: number
  last_seen_at: string | null
  created_at: string
}

/** Qui a le droit de s'appuyer sur CE back-office : faire expedier ses emails,
 *  et remonter ses donnees vers lui. Un meme jeton ouvre les deux, chaque role
 *  restant ferme tant qu'il n'est pas active cote serveur. */
export function RelayClients({ defaultQuota }: { defaultQuota: number }) {
  const [rows, setRows] = useState<Client[]>([])
  const [name, setName] = useState('')
  const [quota, setQuota] = useState(defaultQuota)
  const [fresh, setFresh] = useState<{ name: string; token: string } | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = () => api<Client[]>('/api/admin/relay-clients').then(setRows)
  useEffect(() => {
    load()
  }, [])

  const create = async () => {
    setError(null)
    try {
      const created = await api<Client & { token: string }>('/api/admin/relay-clients', {
        method: 'POST',
        body: JSON.stringify({ name, daily_quota: quota }),
      })
      setFresh({ name: created.name, token: created.token })
      setName('')
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const patch = async (client: Client, body: Partial<Client>) => {
    await api(`/api/admin/relay-clients/${client.id}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    })
    load()
  }

  const remove = async (client: Client) => {
    if (!confirm(`Revoquer definitivement « ${client.name} » ? Son token cessera de fonctionner.`))
      return
    await api(`/api/admin/relay-clients/${client.id}`, { method: 'DELETE' })
    load()
  }

  return (
    <>
      <p className="muted hint">
        Chaque back-office autorise a s'appuyer sur celui-ci — envoi d'emails, remontee
        des donnees — a son propre token, son quota et son interrupteur. Un token suffit :
        il ne se colle que sur des machines de confiance, et se coupe d'ici en un clic.
      </p>

      {fresh && (
        <div className="reveal">
          <p>
            <strong>Token de « {fresh.name} »</strong> — copiez-le maintenant, il ne sera plus
            jamais affiche (seule son empreinte est conservee).
          </p>
          <code>{fresh.token}</code>
          <div className="toolbar">
            <button className="link" onClick={() => navigator.clipboard?.writeText(fresh.token)}>
              Copier
            </button>
            <button className="link" onClick={() => setFresh(null)}>
              J'ai copie le token
            </button>
          </div>
        </div>
      )}

      {error && <p className="error">{error}</p>}

      <div className="toolbar">
        <input
          type="text"
          placeholder="Nom du back-office (ex. Borne Mondial 2026)"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          type="number"
          min={1}
          value={quota}
          onChange={(e) => setQuota(Number(e.target.value))}
          title="Envois maximum par jour"
        />
        <button disabled={!name.trim()} onClick={create}>
          Creer un client
        </button>
      </div>

      {rows.length === 0 ? (
        <p className="muted">Aucun client. Personne ne peut s'appuyer sur ce back-office.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Nom</th>
              <th>Prefixe</th>
              <th>Aujourd'hui</th>
              <th>Total</th>
              <th>Derniere activite</th>
              <th>Etat</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className={row.is_active ? '' : 'row-muted'}>
                <td>{row.name}</td>
                <td>
                  <code>{row.token_prefix}</code>
                </td>
                <td>
                  {row.sent_today} / {row.daily_quota}
                </td>
                <td>{row.sent_total}</td>
                <td className="muted">
                  {row.last_seen_at ? new Date(row.last_seen_at).toLocaleString('fr-FR') : 'jamais'}
                </td>
                <td>
                  <label className="switch inline">
                    <input
                      type="checkbox"
                      checked={row.is_active}
                      onChange={(e) => patch(row, { is_active: e.target.checked })}
                    />
                    <span>{row.is_active ? 'actif' : 'coupe'}</span>
                  </label>
                </td>
                <td>
                  <button className="link" onClick={() => remove(row)}>
                    Revoquer
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}
