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

/** Une creation approuvee, telle que l'API la liste. */
type Creation = { id: string; render_url: string }

/**
 * Les creations approuvees, l'une apres l'autre, en fondu enchaine. Tant
 * qu'aucune ne l'est -- au debut du salon, par exemple -- le tableau de bord
 * reste nu, tel que la photo du studio le montre : on ne le prend ni pour une
 * panne, ni pour la creation de quelqu'un.
 */
function Defilement() {
  const { api, settings } = useApp()
  const catalog = useSession((s) => s.catalog)
  const [liste, setListe] = useState<Creation[]>([])
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

  // Les creations affichees, la plus recente en dernier. Au changement, la
  // suivante s'ajoute par-dessus, invisible ; une fois son image chargee, elle
  // apparait en fondu, puis la precedente est retiree. Chaque calque garde sa
  // cle d'un bout a l'autre : retirer le dessous ne recharge pas le dessus.
  const [calques, setCalques] = useState<{ creation: Creation; visible: boolean }[]>([])
  useEffect(() => {
    if (!courante) {
      setCalques([])
      return
    }
    setCalques((avant) =>
      avant.at(-1)?.creation.id === courante.id
        ? avant
        : // La toute premiere parait d'emblee, sans fondu depuis le vide.
          [...avant.slice(-1), { creation: courante, visible: avant.length === 0 }],
    )
  }, [courante])

  const montrer = (id: string) =>
    // Deux images plus tard : l'opacite nulle doit avoir ete peinte, sans quoi
    // le navigateur saute directement a la fin de la transition.
    requestAnimationFrame(() =>
      requestAnimationFrame(() =>
        setCalques((avant) => avant.map((k) => (k.creation.id === id ? { ...k, visible: true } : k))),
      ),
    )

  if (!catalog?.mockup) return null
  const mockup = catalog.mockup

  // Aucune creation approuvee : la planche de bord nue de la photo.
  if (!calques.length) return <SkinMockup mockup={mockup} shape={catalog.shape} mediaBase={api.mediaBase} />

  return (
    <>
      {calques.map(({ creation, visible }, i) => (
        <div
          key={creation.id}
          className={`fondu ${visible ? 'visible' : ''}`}
          onTransitionEnd={(e) => {
            // Le fondu du dessus est fini : le dessous ne se voit plus.
            if (e.target === e.currentTarget && i === calques.length - 1) setCalques((avant) => avant.slice(-1))
          }}
        >
          <SkinMockup
            mockup={mockup}
            shape={catalog.shape}
            mediaBase={api.mediaBase}
            src={`${api.base}${creation.render_url}`}
            onPret={() => montrer(creation.id)}
            onErreur={() => {
              setManquants((vus) => new Set(vus).add(creation.id))
              setCalques((avant) => avant.filter((k) => k.creation.id !== creation.id))
            }}
          />
        </div>
      ))}
    </>
  )
}
