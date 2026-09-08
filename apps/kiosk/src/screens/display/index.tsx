import { useEffect, useMemo, useState } from 'react'
import { Text, Title } from '@mantine/core'
import { SkinCanvas } from '../../components/SkinCanvas'
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

/** Defilement des fonds du catalogue + appel a jouer, comme prevu au brief. */
function Slideshow({ intervalSeconds }: { intervalSeconds: number }) {
  const { api } = useApp()
  const { t } = useI18n()
  const { catalog } = useSession()
  const [index, setIndex] = useState(0)
  const slides = useMemo(() => catalog?.backgrounds ?? [], [catalog])

  useEffect(() => {
    if (slides.length < 2) return
    const id = window.setInterval(() => setIndex((i) => (i + 1) % slides.length), intervalSeconds * 1000)
    return () => window.clearInterval(id)
  }, [slides.length, intervalSeconds])

  return (
    <div className="display-root attract">
      {slides[index] && <img key={slides[index].id} src={api.asset(slides[index])} alt="" />}
      <div className="attract-overlay">
        <Title order={1} className="display-title">{t('display.attractTitle')}</Title>
        <Text size="xl">{t('display.attractCta')}</Text>
      </div>
    </div>
  )
}
