import { useEffect, useState } from 'react'
import { api } from '../lib/api'

type Row = {
  id: string
  to: string
  subject: string
  status: string
  attempts: number
  last_error: string | null
  created_at: string
  sent_at: string | null
}

export function Emails() {
  const [rows, setRows] = useState<Row[]>([])

  const load = () => api<Row[]>('/api/admin/emails').then(setRows)

  useEffect(() => {
    load()
    const id = setInterval(load, 10_000)
    return () => clearInterval(id)
  }, [])

  return (
    <>
      <h1>File d'envoi</h1>
      <div className="toolbar">
        <button
          onClick={async () => {
            await api('/api/admin/emails/retry-failed', { method: 'POST' })
            load()
          }}
        >
          Relancer les echecs
        </button>
      </div>
      <table>
        <thead>
          <tr><th>Destinataire</th><th>Objet</th><th>Statut</th><th>Essais</th><th>Erreur</th></tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className={row.status === 'failed' ? 'row-alert' : ''}>
              <td>{row.to}</td>
              <td>{row.subject}</td>
              <td>{row.status}</td>
              <td>{row.attempts}</td>
              <td className="muted">{row.last_error ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}
