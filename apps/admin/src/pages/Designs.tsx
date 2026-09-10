import { useEffect, useState } from 'react'
import { api } from '../lib/api'

type Row = {
  id: string
  status: string
  created_at: string
  render_url: string | null
  visitor_name: string | null
  visitor_email: string | null
  moderation: 'pending' | 'approved' | 'rejected'
  moderated_at: string | null
}

type Compteurs = { pending: number; approved: number; rejected: number }

// Le second onglet est preselectionne sur « validees » : c'est ce qu'on vient
// verifier neuf fois sur dix, le rejet etant l'exception qu'on releit rarement.
const VERDICTS = [
  { value: 'approved', label: 'Validees' },
  { value: 'rejected', label: 'Rejetees' },
]

const TRIS = [
  { value: 'date_desc', label: 'Plus recentes' },
  { value: 'date_asc', label: 'Plus anciennes' },
  { value: 'name_asc', label: 'Nom (A-Z)' },
  { value: 'name_desc', label: 'Nom (Z-A)' },
]

const date = (iso: string) => new Date(iso).toLocaleString('fr-FR')

export function Designs() {
  const [rows, setRows] = useState<Row[]>([])
  const [total, setTotal] = useState(0)
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState('date_desc')
  const [agrandie, setAgrandie] = useState<number | null>(null)
  const [onglet, setOnglet] = useState<'attente' | 'traitees'>('attente')
  const [verdict, setVerdict] = useState('approved')
  const [compteurs, setCompteurs] = useState<Compteurs>({ pending: 0, approved: 0, rejected: 0 })
  const [rafraichir, setRafraichir] = useState(0)

  const moderation = onglet === 'attente' ? 'pending' : verdict

  useEffect(() => {
    api<Compteurs>('/api/admin/designs/counts').then(setCompteurs)
  }, [rafraichir])

  useEffect(() => {
    const id = setTimeout(() => {
      const q = new URLSearchParams({ limit: '60', search, sort, moderation })
      api<{ total: number; items: Row[] }>(`/api/admin/designs?${q}`).then((res) => {
        setRows(res.items)
        setTotal(res.total)
        // La liste vient de changer sous la loupe : l'index pointerait une
        // autre creation, ou plus rien du tout.
        setAgrandie(null)
      })
    }, 250)
    return () => clearTimeout(id)
  }, [search, sort, moderation, rafraichir])

  /** Verdict de l'animateur. La creation quitte alors l'onglet ou elle etait. */
  const decider = async (id: string, decision: Row['moderation']) => {
    await api(`/api/admin/designs/${id}/moderation`, {
      method: 'POST',
      body: JSON.stringify({ decision }),
    })
    setRafraichir((n) => n + 1)
  }

  // On ne navigue qu'entre les creations reellement rendues : une vignette en
  // echec n'a pas d'image a agrandir.
  const rendues = rows.filter((row) => row.render_url)

  const deplacer = (pas: number) =>
    setAgrandie((i) => Math.min(rendues.length - 1, Math.max(0, (i ?? 0) + pas)))

  useEffect(() => {
    if (agrandie === null) return
    const touche = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setAgrandie(null)
      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
        // Sans ca, la fleche fait AUSSI defiler la grille restee dessous : on
        // referme l'agrandissement a un tout autre endroit de la liste.
        e.preventDefault()
        deplacer(e.key === 'ArrowLeft' ? -1 : 1)
      }
    }
    window.addEventListener('keydown', touche)
    return () => window.removeEventListener('keydown', touche)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agrandie, rendues.length])

  // Effet separe : sur `agrandie`, il se rejouerait a chaque fleche et
  // finirait par « restaurer » le blocage qu'il vient lui-meme de poser.
  const ouvert = agrandie !== null
  useEffect(() => {
    if (!ouvert) return
    const precedent = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = precedent
    }
  }, [ouvert])

  const ouverte = agrandie === null ? null : rendues[agrandie]

  return (
    <>
      <h1>Creations <span className="muted">({total})</span></h1>

      <nav className="onglets">
        <button
          type="button"
          className={onglet === 'attente' ? 'actif' : ''}
          onClick={() => setOnglet('attente')}
        >
          A moderer <span className="pastille">{compteurs.pending}</span>
        </button>
        <button
          type="button"
          className={onglet === 'traitees' ? 'actif' : ''}
          onClick={() => setOnglet('traitees')}
        >
          Traitees <span className="pastille">{compteurs.approved + compteurs.rejected}</span>
        </button>
      </nav>

      <div className="toolbar">
        <input
          placeholder="Filtrer par nom, prenom ou email"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          aria-label="Trier les creations"
          value={sort}
          onChange={(e) => setSort(e.target.value)}
        >
          {TRIS.map((tri) => (
            <option key={tri.value} value={tri.value}>{tri.label}</option>
          ))}
        </select>
        {onglet === 'traitees' && (
          <select
            aria-label="Filtrer par verdict"
            value={verdict}
            onChange={(e) => setVerdict(e.target.value)}
          >
            {VERDICTS.map((v) => (
              <option key={v.value} value={v.value}>{v.label}</option>
            ))}
          </select>
        )}
      </div>

      {rows.length === 0 && (
        <p className="muted">
          {onglet === 'attente' && !search
            ? 'Rien a moderer : tout a ete traite.'
            : 'Aucune creation ne correspond.'}
        </p>
      )}

      <div className="grid">
        {rows.map((row) => (
          <figure key={row.id} className={row.status === 'rendered' ? '' : 'failed'}>
            {row.render_url ? (
              <button
                type="button"
                className="vignette"
                title="Agrandir"
                onClick={() => setAgrandie(rendues.findIndex((r) => r.id === row.id))}
              >
                <img src={row.render_url} alt="" loading="lazy" />
              </button>
            ) : (
              <div className="placeholder">{row.status}</div>
            )}
            <figcaption>
              {/* Sans nom : le visiteur a ete supprime (RGPD) ou la creation
                  a ete faite en mode demo, sans inscription. */}
              <strong>{row.visitor_name ?? 'Anonyme'}</strong>
              {row.visitor_email && <span className="email">{row.visitor_email}</span>}
              <span>{date(row.created_at)}</span>
            </figcaption>

            {onglet === 'attente' ? (
              <div className="verdict">
                <button type="button" className="valider" onClick={() => decider(row.id, 'approved')}>
                  Valider
                </button>
                <button type="button" className="rejeter" onClick={() => decider(row.id, 'rejected')}>
                  Rejeter
                </button>
              </div>
            ) : (
              <div className="verdict">
                {/* Reversible : un clic de travers se rattrape sans passer par
                    la base, et la creation revient dans l'onglet d'en face. */}
                <span className={row.moderation === 'approved' ? 'ok' : 'ko'}>
                  {row.moderation === 'approved' ? 'Validee' : 'Rejetee'}
                </span>
                <button
                  type="button"
                  className="link"
                  onClick={() =>
                    decider(row.id, row.moderation === 'approved' ? 'rejected' : 'approved')
                  }
                >
                  {row.moderation === 'approved' ? 'Rejeter' : 'Valider'}
                </button>
              </div>
            )}
          </figure>
        ))}
      </div>

      {ouverte && (
        <div className="lightbox" role="dialog" aria-modal="true" onClick={() => setAgrandie(null)}>
          <button type="button" className="fermer" aria-label="Fermer" onClick={() => setAgrandie(null)}>
            &times;
          </button>
          <figure onClick={(e) => e.stopPropagation()}>
            <img src={ouverte.render_url!} alt="" />
            <figcaption>
              <strong>{ouverte.visitor_name ?? 'Anonyme'}</strong>
              {ouverte.visitor_email && <span>{ouverte.visitor_email}</span>}
              <span>{date(ouverte.created_at)}</span>
              <a href={ouverte.render_url!} target="_blank" rel="noreferrer">Ouvrir le JPEG</a>
            </figcaption>
          </figure>
          <nav onClick={(e) => e.stopPropagation()}>
            <button
              type="button"
              disabled={agrandie === 0}
              onClick={() => deplacer(-1)}
            >
              Precedente
            </button>
            <span className="muted">{(agrandie ?? 0) + 1} / {rendues.length}</span>
            <button
              type="button"
              disabled={agrandie === rendues.length - 1}
              onClick={() => deplacer(1)}
            >
              Suivante
            </button>
          </nav>
        </div>
      )}
    </>
  )
}
