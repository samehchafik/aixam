import { useEffect, useState } from 'react'
import { Ribbon } from '../../components/chrome/Ribbon'
import { TableauDeBord } from '../../components/TableauDeBord'
import { useFondEcran } from '../../components/Stage16x9'
import { useDecorVoiture } from '../../components/voiture'
import { useApp } from '../../app-context'
import type { Layer } from '../../api/client'
import bandeauMarque from '../../assets/bandeau-marque.png'

/**
 * Ce que montre le grand ecran. `layers` garde la derniere composition recue :
 * apres la validation, la creation reste sur la voiture le temps que le
 * visiteur la voie, puis le diaporama reprend.
 */
type Mode = { kind: 'attract' } | { kind: 'live' | 'finished'; layers: Layer[] }

/** Duree pendant laquelle une creation validee reste affichee. */
const APRES_VALIDATION_MS = 20_000

/**
 * Grand ecran. Il garde toujours son habillage -- la photo, le bandeau de
 * marque, la vague du haut. Sur la planche de bord, les creations approuvees
 * defilent quand personne ne joue ; des qu'un visiteur compose, c'est la
 * sienne, en direct.
 */
export function DisplayScreen() {
  const { bus } = useApp()
  const [mode, setMode] = useState<Mode>({ kind: 'attract' })
  useFondEcran(useDecorVoiture())

  useEffect(() => {
    const off = bus.on((message) => {
      if (message.type === 'idle') setMode({ kind: 'attract' })
      if (message.type === 'state') setMode({ kind: 'live', layers: message.layers as Layer[] })
      // La validation n'apporte pas de calques : on garde ceux qu'on montrait.
      // Un ecran redemarre entre-temps n'a rien a montrer, et repart sur le
      // diaporama.
      if (message.type === 'finished')
        setMode((avant) => (avant.kind === 'attract' ? avant : { kind: 'finished', layers: avant.layers }))
    })
    return () => {
      off()
    }
  }, [bus])

  useEffect(() => {
    if (mode.kind !== 'finished') return
    const id = window.setTimeout(() => setMode({ kind: 'attract' }), APRES_VALIDATION_MS)
    return () => window.clearTimeout(id)
  }, [mode.kind])

  // L'ecran 1 du tactile, sans ce qui ne sert qu'au doigt -- ni bouton, ni
  // fleche qui y mene.
  return (
    <div className="ecran">
      <TableauDeBord layers={mode.kind === 'attract' ? undefined : mode.layers} />
      <img className="bandeau-marque" src={bandeauMarque} alt="" draggable={false} />
      <Ribbon modele="diaporama" />
    </div>
  )
}
