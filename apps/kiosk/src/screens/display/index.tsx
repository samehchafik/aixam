import { useEffect, useState } from 'react'
import { Text, Title } from '@mantine/core'
import { SkinCanvas } from '../../components/SkinCanvas'
import { PlancheDefilante } from '../../components/PlancheDefilante'
import { Ribbon } from '../../components/chrome/Ribbon'
import { Fond } from '../../components/Stage16x9'
import { useApp } from '../../app-context'
import { useI18n } from '../../i18n'
import { useSession } from '../../state/session'
import type { Layer } from '../../api/client'
import fondBorne from '../../assets/fond-borne.avif'
import bandeauMarque from '../../assets/bandeau-marque.png'

type Mode =
  | { kind: 'attract' }
  | { kind: 'live'; layers: Layer[]; firstName?: string }
  | { kind: 'finished'; renderUrl: string | null }

const SKIN_WIDTH = 1760

/**
 * Grand ecran. Deux etats : diaporama d'attente quand personne ne joue,
 * miroir de la composition en cours sinon.
 */
export function DisplayScreen() {
  const { api, bus } = useApp()
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

  // Apres une creation terminee, on repart sur le diaporama tout seul.
  useEffect(() => {
    if (mode.kind !== 'finished') return
    const id = window.setTimeout(() => setMode({ kind: 'attract' }), 20_000)
    return () => window.clearTimeout(id)
  }, [mode.kind])

  const diaporama = mode.kind === 'attract' || (mode.kind === 'finished' && !mode.renderUrl)

  if (!catalog) return <div className="display-root" />
  if (diaporama) return <Diaporama />

  if (mode.kind === 'finished') {
    return (
      <div className="display-root finished">
        <img src={mode.renderUrl!} alt="" />
        <Title order={2} className="display-cta">{t('display.shareCta')}</Title>
      </div>
    )
  }

  return (
    <div className="display-root live">
      <Fond src={fondBorne} />
      {mode.firstName && <Text className="display-who">{t('display.creationOf', { firstName: mode.firstName })}</Text>}
      <SkinCanvas catalog={catalog} layers={mode.layers} mediaBase={api.mediaBase} skinWidth={SKIN_WIDTH} bleed={20} />
    </div>
  )
}

/**
 * L'attente : l'ecran 1 du tactile, sans ce qui ne sert qu'au doigt -- ni
 * bouton, ni fleche qui y mene.
 */
function Diaporama() {
  return (
    <div className="ecran">
      <PlancheDefilante />
      <img className="bandeau-marque" src={bandeauMarque} alt="" draggable={false} />
      <Ribbon modele="diaporama" />
    </div>
  )
}
