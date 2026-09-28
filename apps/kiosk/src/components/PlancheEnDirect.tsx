import { useApp } from '../app-context'
import { useSession } from '../state/session'
import type { Layer } from '../api/client'
import { SkinCanvas } from './SkinCanvas'
import { SkinMockup } from './SkinMockup'

/**
 * La planche de bord photographiee, portant une creation dessinee en direct
 * a partir de ses calques -- pas de rendu serveur a attendre. Pendant de
 * `PlancheDefilante` : l'ecran 7 du tactile y montre la creation avant
 * l'envoi, le grand ecran celle qu'un visiteur est en train de composer.
 */
export function PlancheEnDirect({ layers }: { layers: Layer[] }) {
  const { api } = useApp()
  const catalog = useSession((s) => s.catalog)
  if (!catalog?.mockup) return null
  return (
    <SkinMockup mockup={catalog.mockup} shape={catalog.shape} mediaBase={api.mediaBase}>
      <SkinCanvas catalog={catalog} layers={layers} mediaBase={api.mediaBase} skinWidth={catalog.shape.width} contour={0} />
    </SkinMockup>
  )
}
