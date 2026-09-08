import { useEffect, useState } from 'react'
import { api } from '../lib/api'

type Row = {
  id: string
  first_name: string
  last_name: string
  email: string
  postal_code: string
  email_verified_at: string | null
  consent_marketing: boolean
  created_at: string
}

export function Visitors() {
  const [rows, setRows] = useState<Row[]>([])
  const [total, setTotal] = useState(0)
  const [search, setSearch] = useState('')

  const load = () =>
    api<{ total: number; items: Row[] }>(
      `/api/admin/visitors?limit=100&search=${encodeURIComponent(search)}`,
    ).then((res) => {
      setRows(res.items)
      setTotal(res.total)
    })

  useEffect(() => {
    const id = setTimeout(load, 250)
    return () => clearTimeout(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search])

  const remove = async (id: string) => {
    if (!confirm('Supprimer definitivement ce visiteur (demande RGPD) ?')) return
    await api(`/api/admin/visitors/${id}`, { method: 'DELETE' })
    load()
  }

  return (
    <>
      <h1>Visiteurs <span className="muted">({total})</span></h1>
      <div className="toolbar">
        <input
          placeholder="Rechercher nom ou email"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <a className="button" href="/api/admin/visitors.csv?consented_only=true">
          Export CSV (opt-in)
        </a>
      </div>

      <table>
        <thead>
          <tr>
            <th>Nom</th><th>Email</th><th>CP</th><th>Verifie</th><th>Opt-in</th><th>Date</th><th />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>{row.first_name} {row.last_name}</td>
              <td>{row.email}</td>
              <td>{row.postal_code}</td>
              <td>{row.email_verified_at ? 'oui' : '—'}</td>
              <td>{row.consent_marketing ? 'oui' : '—'}</td>
              <td>{new Date(row.created_at).toLocaleString('fr-FR')}</td>
              <td><button className="link" onClick={() => remove(row.id)}>Supprimer</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}
