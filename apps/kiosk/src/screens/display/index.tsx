import { useEffect, useState } from 'react'
import { PlancheDefilante } from '../../components/PlancheDefilante'
import { Ribbon } from '../../components/chrome/Ribbon'
import { PlancheEnGrand } from '../../components/PlancheEnGrand'
import { useApp } from '../../app-context'
import type { Layer } from '../../api/client'
import bandeauMarque from '../../assets/bandeau-marque.png'

/**
 * Ce que montre le grand ecran. `layers` garde la derniere composition recue :
 * apres la validation, la creation reste affichee le temps que le visiteur la
 * voie, puis disparait.
 */
type Mode = { kind: 'attract' } | { kind: 'live' | 'finished'; layers: Layer[] }

/** Duree pendant laquelle une creation validee reste affichee. */
const APRES_VALIDATION_MS = 20_000

/**
 * Grand ecran. Le diaporama y tourne en permanence : la photo, le bandeau de
 * marque, la vague du haut, et les creations approuvees qui defilent sur le
 * tableau de bord. Des qu'un visiteur compose, sa creation vient PAR-DESSUS,
 * en grand, dans la planche du bas de l'ecran 7 -- sans son bouton.
 */
export function DisplayScreen() {
  const { bus } = useApp()
  const [mode, setMode] = useState<Mode>({ kind: 'attract' })

  useEffect(() => {
    const off = bus.on((message) => {
      if (message.type === 'idle') setMode({ kind: 'attract' })
      if (message.type === 'state') setMode({ kind: 'live', layers: message.layers as Layer[] })
      // La validation n'apporte pas de calques : on garde ceux qu'on montrait.
      // Un ecran redemarre entre-temps n'a rien a montrer, et reste sur le
      // diaporama seul.
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
      <PlancheDefilante />
      <img className="bandeau-marque" src={bandeauMarque} alt="" draggable={false} />
      <Ribbon modele="diaporama" />
      {mode.kind !== 'attract' && <PlancheEnGrand layers={mode.layers} />}
    </div>
  )
}
