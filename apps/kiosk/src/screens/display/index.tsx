import { useEffect, useMemo, useState } from 'react'
import { Text, Title } from '@mantine/core'
import { SkinCanvas } from '../../components/SkinCanvas'
import { SkinMockup } from '../../components/SkinMockup'
import { useApp } from '../../app-context'
import { useI18n } from '../../i18n'
import { useSession } from '../../state/session'
import type { Layer } from '../../api/client'

type Mode =
  | { kind: 'attract' }
  | { kind: 'live'; layers: Layer[]; firstName?: string }
  | { kind: 'finished'; renderUrl: string | null }

const SKIN_WIDTH = 1760

/**
 * Grand ecran. Deux etats : slideshow d'attente quand personne ne joue,
 * miroir de la composition en cours sinon.
 */
export function DisplayScreen() {
  const { api, bus, settings } = useApp()
  const { t } = useI18n()
  const { catalog } = useSession()
  const [mode, setMode] = useState<Mode>({ kind: 'attract' })

  useEffect(() => {
    const off = bus.on((message) => {
      if (message.type === 'idle') setMode({ kind: 'attract' })
      if (message.type === 'state')
        setMode({ kind: 'live', layers: message.layers as Layer[], firstName: message.firstName })
      if (message.type === 'finished') setMode({ kind: 'finished', renderUrl: message.renderUrl })
    })
    return () => {
      off()
    }
  }, [bus])

  // Apres une creation terminee, on repart sur le slideshow tout seul.
  useEffect(() => {
    if (mode.kind !== 'finished') return
    const id = window.setTimeout(() => setMode({ kind: 'attract' }), 20_000)
    return () => window.clearTimeout(id)
  }, [mode.kind])

  if (!catalog) return <div className="display-root" />

  if (mode.kind === 'finished') {
    if (!mode.renderUrl) return <Slideshow intervalSeconds={settings.attract_interval_seconds} />
    return (
      <div className="display-root finished">
        <img src={mode.renderUrl} alt="" />
        <Title order={2} className="display-cta">{t('display.shareCta')}</Title>
      </div>
    )
  }

  if (mode.kind === 'attract') return <Slideshow intervalSeconds={settings.attract_interval_seconds} />

  return (
    <div className="display-root live">
      {mode.firstName && <Text className="display-who">{t('display.creationOf', { firstName: mode.firstName })}</Text>}
      <SkinCanvas catalog={catalog} layers={mode.layers} mediaBase={api.mediaBase} skinWidth={SKIN_WIDTH} bleed={20} />
    </div>
  )
}

/**
 * L'attente : les creations des visiteurs defilent, posees sur la planche de
 * bord. Tant qu'aucune n'a ete approuvee -- au debut du salon, par exemple --
 * ce sont les fonds du catalogue qui defilent, poses sur la meme planche : la
 * voiture est la des la premiere minute, et l'ecran ne donne jamais
 * l'impression d'etre en panne.
 */
function Slideshow({ intervalSeconds }: { intervalSeconds: number }) {
  const { api } = useApp()
  const { t } = useI18n()
  const { catalog } = useSession()
  const [creations, setCreations] = useState<{ id: string; render_url: string }[]>([])
  const [index, setIndex] = useState(0)

  // La liste est relue de temps en temps : une creation approuvee pendant le
  // salon doit rejoindre le defilement sans qu'on redemarre l'ecran.
  useEffect(() => {
    let vivant = true
    const charger = () =>
      api
        .creationsRecentes()
        .then((liste) => vivant && setCreations(liste))
        .catch(() => {})
    charger()
    const id = window.setInterval(charger, 60_000)
    return () => {
      vivant = false
      window.clearInterval(id)
    }
  }, [api])

  const fonds = useMemo(() => catalog?.backgrounds ?? [], [catalog])
  const total = creations.length || fonds.length

  useEffect(() => {
    if (total < 2) return
    const id = window.setInterval(() => setIndex((i) => (i + 1) % total), intervalSeconds * 1000)
    return () => window.clearInterval(id)
  }, [total, intervalSeconds])

  const courante = creations[index % Math.max(1, creations.length)]
  const fond = fonds[index % Math.max(1, fonds.length)]
  const mockup = catalog?.mockup

  return (
    <div className="display-root attract">
      {mockup && catalog && (
        <SkinMockup
          key={courante?.id ?? fond?.id}
          mockup={mockup}
          shape={catalog.shape}
          mediaBase={api.mediaBase}
          src={courante ? `${api.base}${courante.render_url}` : undefined}
        >
          {/* Aucune creation approuvee : on pose un fond du catalogue sur la
              planche. L'ecran montre la voiture des le premier jour, au lieu
              d'un repli qu'on prendrait pour une panne. */}
          {!courante && fond && <img src={api.asset(fond)} alt="" />}
        </SkinMockup>
      )}
      <div className="attract-overlay">
        <Title order={1} className="display-title">{t('display.attractTitle')}</Title>
        <Text size="xl">{t('display.attractCta')}</Text>
      </div>
    </div>
  )
}
