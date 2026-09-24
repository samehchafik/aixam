import type { ReactNode } from 'react'
import { Fond } from '../../components/Stage16x9'
import { Ribbon } from '../../components/chrome/Ribbon'
import fondFormulaire from '../../assets/fond-formulaire.avif'

/**
 * Le decor commun des ecrans 2 et 3 : l'habitacle assombri, la planche
 * « Freedom » et le bandeau dont la fleche vise la carte bleue.
 */
export function EcranFormulaire({ children }: { children: ReactNode }) {
  return (
    <div className="ecran">
      <Fond src={fondFormulaire} />
      <Ribbon modele="formulaire" />
      {children}
    </div>
  )
}
