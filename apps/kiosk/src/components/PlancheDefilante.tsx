import { useEffect, useMemo, useState } from 'react'
import { useApp } from '../app-context'
import { useSession } from '../state/session'
import { SkinMockup } from './SkinMockup'

/**
 * La planche de bord photographiee, sur laquelle defilent les creations
 * approuvees. C'est le diaporama du grand ecran, et le fond de l'accueil du
 * tactile.
 *
 * Tant qu'aucune n'a ete approuvee -- au debut du salon, par exemple -- la
 * planche reste noire. La voiture est la des la premiere minute, et un skin
 * noir est une planche neuve : on ne le prend ni pour une panne, ni pour la
 * creation de quelqu'un.
 */
export function PlancheDefilante() {
  const { api, settings } = useApp()
  const { catalog } = useSession()
  const [liste, setListe] = useState<{ id: string; render_url: string }[]>([])
  // Un rendu peut disparaitre entre la reponse de l'API et son affichage. On
  // retient celui qui a echoue pour ne pas y revenir a chaque tour.
  const [manquants, setManquants] = useState<Set<string>>(new Set())
  const [index, setIndex] = useState(0)

  // La liste est relue de temps en temps : une creation approuvee pendant le
  // salon doit rejoindre le defilement sans qu'on redemarre l'ecran.
  useEffect(() => {
    let vivant = true
    const charger = () =>
      api
        .creationsRecentes()
        .then((recues) => vivant && setListe(recues))
        .catch(() => {})
    charger()
    const id = window.setInterval(charger, 60_000)
    return () => {
      vivant = false
      window.clearInterval(id)
    }
  }, [api])

  const creations = useMemo(() => liste.filter((c) => !manquants.has(c.id)), [liste, manquants])
  const total = creations.length

  useEffect(() => {
    if (total < 2) return
    const id = window.setInterval(() => setIndex((i) => (i + 1) % total), settings.attract_interval_seconds * 1000)
    return () => window.clearInterval(id)
  }, [total, settings.attract_interval_seconds])

  const courante = creations[index % Math.max(1, total)]
  if (!catalog?.mockup) return null

  return (
    <SkinMockup
      // Sans creation approuvee, aucun skin n'est pose : la zone du mockup
      // laisse voir son fond noir, et la planche parait neuve.
      key={courante?.id ?? 'vide'}
      mockup={catalog.mockup}
      shape={catalog.shape}
      mediaBase={api.mediaBase}
      src={courante ? `${api.base}${courante.render_url}` : undefined}
      onErreur={() => courante && setManquants((vus) => new Set(vus).add(courante.id))}
    />
  )
}
