import { useEffect, useState } from 'react'
import { api } from '../lib/api'

type Row = {
  id: string
  status: string
  created_at: string
  render_url: string | null
  visitor_name: string | null
  visitor_email: string | null
}

export function Designs() {
  const [rows, setRows] = useState<Row[]>([])

  useEffect(() => {
    api<{ items: Row[] }>('/api/admin/designs?limit=60').then((res) => setRows(res.items))
  }, [])

  return (
    <>
      <h1>Creations</h1>
      <div className="grid">
        {rows.map((row) => (
          <figure key={row.id} className={row.status === 'rendered' ? '' : 'failed'}>
            {row.render_url ? (
              <img src={row.render_url} alt="" loading="lazy" />
            ) : (
              <div className="placeholder">{row.status}</div>
            )}
            <figcaption>
              {/* Sans nom : le visiteur a ete supprime (RGPD) ou la creation
                  a ete faite en mode demo, sans inscription. */}
              <strong>{row.visitor_name ?? 'Anonyme'}</strong>
              {row.visitor_email && <span className="email">{row.visitor_email}</span>}
              <span>{new Date(row.created_at).toLocaleString('fr-FR')}</span>
            </figcaption>
          </figure>
        ))}
      </div>
    </>
  )
}
