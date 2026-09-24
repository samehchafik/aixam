import type { Catalog } from '../api/client'
import { useSession, type Step } from './session'

/**
 * Developpement seulement : `?etape=review` ouvre directement un ecran du
 * parcours, pour le comparer a la maquette sans refaire tout le chemin. Les
 * ecrans qui montrent une creation recoivent le premier fond du catalogue.
 *
 * Appele sous `import.meta.env.DEV` : le build de production l'elimine.
 */
export function etapeDeDemo(catalog: Catalog) {
  const etape = new URLSearchParams(window.location.search).get('etape') as Step | null
  if (!etape) return
  const session = useSession.getState()
  if ((etape === 'editor' || etape === 'review') && catalog.backgrounds[0]) {
    session.setBackground({ assetId: catalog.backgrounds[0].id })
    session.select(null)
  }
  if (etape === 'verify') session.setVisitor('demo', 'Anne')
  session.setStep(etape)
}
