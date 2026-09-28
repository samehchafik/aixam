import type { ReactNode } from 'react'
import { useApp } from '../app-context'
import { useSession } from '../state/session'
import type { Layer } from '../api/client'
import { Ribbon } from './chrome/Ribbon'
import { SkinCanvas } from './SkinCanvas'
import { SkinMockup } from './SkinMockup'
import logoBasDroite from '../assets/logo-bas-droite.png'

/**
 * La planche du bas, relevee sur l'ecran 7 : la meme que celle de l'editeur,
 * un peu plus large et au contour un peu plus epais, pour la detacher de la
 * photo.
 */
const PLANCHE = { x: 103, y: 747, largeur: 1714, contour: 4 }

/**
 * Une creation posee sur la voiture, et en grand dans la planche du bas :
 * l'ecran 7 du studio. Le tactile y ajoute ses boutons (`children`) ; le
 * grand ecran la montre telle quelle, pendant qu'un visiteur compose.
 */
export function SceneVoiture({ layers, children }: { layers: Layer[]; children?: ReactNode }) {
  const { api } = useApp()
  const catalog = useSession((s) => s.catalog)
  if (!catalog) return null

  const hauteur = PLANCHE.largeur * (catalog.shape.height / catalog.shape.width)
  // Le contour deborde de la planche de sa demi-epaisseur : le canvas lui
  // laisse cette place, sans quoi il serait rogne sur les bords.
  const bord = PLANCHE.contour

  return (
    <div className="ecran">
      {catalog.mockup && (
        <SkinMockup mockup={catalog.mockup} shape={catalog.shape} mediaBase={api.mediaBase}>
          <SkinCanvas catalog={catalog} layers={layers} mediaBase={api.mediaBase} skinWidth={catalog.shape.width} contour={0} />
        </SkinMockup>
      )}
      <img className="logo-bas-droite" src={logoBasDroite} alt="" draggable={false} />
      <Ribbon modele="editeur" />

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

      {children}
    </div>
  )
}
