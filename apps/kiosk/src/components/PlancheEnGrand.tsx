import { useApp } from '../app-context'
import { useSession } from '../state/session'
import type { Layer } from '../api/client'
import { SkinCanvas } from './SkinCanvas'

/**
 * La planche du bas, relevee sur l'ecran 7 : la meme que celle de l'editeur,
 * un peu plus large et au contour un peu plus epais, pour la detacher de la
 * photo.
 */
const PLANCHE = { x: 103, y: 747, largeur: 1714, contour: 4 }

/**
 * Une creation en grand, posee en bas de l'ecran par-dessus la photo : c'est
 * la planche de l'ecran 7. Le tactile y montre la creation avant l'envoi, le
 * grand ecran celle qu'un visiteur compose, pendant que les creations
 * approuvees continuent de defiler sur le tableau de bord derriere.
 */
export function PlancheEnGrand({ layers }: { layers: Layer[] }) {
  const { api } = useApp()
  const catalog = useSession((s) => s.catalog)
  if (!catalog) return null

  const hauteur = PLANCHE.largeur * (catalog.shape.height / catalog.shape.width)
  // Le contour deborde de la planche de sa demi-epaisseur : le canvas lui
  // laisse cette place, sans quoi il serait rogne sur les bords.
  const bord = PLANCHE.contour

  return (
    <div className="revue-planche" style={{ left: PLANCHE.x - bord, top: PLANCHE.y - bord }}>
      <SkinCanvas
        catalog={catalog}
        layers={layers}
        mediaBase={api.mediaBase}
        skinWidth={PLANCHE.largeur}
        stage={{ width: PLANCHE.largeur + bord * 2, height: hauteur + bord * 2 }}
        origin={{ x: bord, y: bord }}
        contour={PLANCHE.contour}
      />
    </div>
  )
}
