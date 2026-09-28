import { useApp } from '../app-context'
import { useSession } from '../state/session'
import { urlMockup } from './SkinMockup'

/**
 * La photo de l'habitacle, telle que le catalogue la decrit : le grand ecran
 * et les ecrans 1 et 7 du tactile la partagent. Chaine vide tant que le studio
 * n'a pas livre de decor.
 */
export function useDecorVoiture(): string {
  const { api } = useApp()
  const mockup = useSession((s) => s.catalog?.mockup)
  return mockup ? urlMockup(mockup, api.mediaBase, mockup.decor) : ''
}
