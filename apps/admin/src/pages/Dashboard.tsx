import { useEffect, useState } from 'react'
import { api, type Stats } from '../lib/api'

export function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [timeline, setTimeline] = useState<{ bucket: string; name: string; count: number }[]>([])

  useEffect(() => {
    const load = () => {
      api<Stats>('/api/admin/stats').then(setStats).catch(() => {})
      api<typeof timeline>('/api/admin/timeline?hours=24').then(setTimeline).catch(() => {})
    }
    load()
    const id = setInterval(load, 15_000)
    return () => clearInterval(id)
  }, [])

  if (!stats) return <p className="muted">Chargement...</p>

  const cards = [
    { label: 'Visiteurs inscrits', value: stats.visitors_total },
    { label: 'Emails verifies', value: stats.visitors_verified },
    { label: 'Creations', value: stats.designs_total },
    { label: 'Rendus JPEG', value: stats.designs_rendered },
    { label: 'Emails en attente', value: stats.emails_pending },
    { label: 'Emails en echec', value: stats.emails_failed, alert: stats.emails_failed > 0 },
  ]

  const submitted = timeline.filter((row) => row.name === 'design_submitted')
  const peak = Math.max(1, ...submitted.map((row) => row.count))

  return (
    <>
      <h1>Tableau de bord</h1>
      <div className="cards">
        {cards.map((card) => (
          <div key={card.label} className={card.alert ? 'card alert' : 'card'}>
            <p className="value">{card.value}</p>
            <p className="label">{card.label}</p>
          </div>
        ))}
      </div>

      <h2>Creations par heure (24 h)</h2>
      <div className="bars">
        {submitted.length === 0 && <p className="muted">Aucune donnee sur la periode.</p>}
        {submitted.map((row) => (
          <div key={row.bucket} className="bar" title={`${row.count} creations`}>
            <div style={{ height: `${(row.count / peak) * 100}%` }} />
            <span>{new Date(row.bucket).getHours()}h</span>
          </div>
        ))}
      </div>
    </>
  )
}
