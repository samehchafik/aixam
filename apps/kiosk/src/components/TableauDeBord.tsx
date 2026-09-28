import { useEffect, useMemo, useState } from 'react'
import { useApp } from '../app-context'
import { useSession } from '../state/session'
import type { Layer } from '../api/client'
import { SkinCanvas } from './SkinCanvas'
import { SkinMockup } from './SkinMockup'

/**
 * Le tableau de bord photographie, et ce qui s'y pose. Un seul composant pour
 * tous les ecrans qui le montrent : l'accueil et l'ecran 7 du tactile, le
 * grand ecran. La perspective (`SkinMockup`, les coins de `mockup/index.json`)
 * est donc la meme partout.
 *
 *   sans `layers`  les creations approuvees defilent (accueil, grand ecran
 *                  au repos)
 *   avec `layers`  la creation en cours, dessinee en direct a partir de ses
 *                  calques -- pas de rendu serveur a attendre (ecran 7, grand
 *                  ecran pendant qu'un visiteur compose)
 */
export function TableauDeBord({ layers }: { layers?: Layer[] }) {
  return layers ? <EnDirect layers={layers} /> : <Defilement />
}

function EnDirect({ layers }: { layers: Layer[] }) {
  const { api } = useApp()
  const catalog = useSession((s) => s.catalog)
  if (!catalog?.mockup) return null
  return (
    <SkinMockup mockup={catalog.mockup} shape={catalog.shape} mediaBase={api.mediaBase}>
      <SkinCanvas catalog={catalog} layers={layers} mediaBase={api.mediaBase} skinWidth={catalog.shape.width} contour={0} />
    </SkinMockup>
  )
}

/**
 * Les creations approuvees, l'une apres l'autre. Tant qu'aucune ne l'est --
 * au debut du salon, par exemple -- le tableau de bord reste nu, tel que la
 * photo du studio le montre : on ne le prend ni pour une panne, ni pour la
 * creation de quelqu'un.
 */
function Defilement() {
  const { api, settings } = useApp()
  const catalog = useSession((s) => s.catalog)
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
      key={courante?.id ?? 'vide'}
      mockup={catalog.mockup}
      shape={catalog.shape}
      mediaBase={api.mediaBase}
      src={courante ? `${api.base}${courante.render_url}` : undefined}
      onErreur={() => courante && setManquants((vus) => new Set(vus).add(courante.id))}
    />
  )
}
