import { useI18n } from '../../i18n'
import { useSession } from '../../state/session'
import { useFondEcran } from '../../components/Stage16x9'
import { PlancheDefilante } from '../../components/PlancheDefilante'
import { Ribbon } from '../../components/chrome/Ribbon'
import { useDecorVoiture } from '../../components/voiture'
import bandeauMarque from '../../assets/bandeau-marque.png'
import logoEasy from '../../assets/logo-easy.svg'

/**
 * Ecran 1 : le diaporama du grand ecran, habille pour le tactile -- le
 * bandeau de marque, la fleche et le bouton n'existent qu'ici.
 *
 * Tout l'ecran lance la partie, pas seulement le bouton : sur un salon, on
 * touche la ou l'on regarde.
 */
export function AttractStep() {
  const { t } = useI18n()
  const startSession = useSession((s) => s.startSession)
  useFondEcran(useDecorVoiture())

  return (
    <div className="ecran" onClick={startSession}>
      <PlancheDefilante />
      <img className="bandeau-marque" src={bandeauMarque} alt="" draggable={false} />
      <Ribbon modele="accueil" />
      <button type="button" className="bouton bouton-bleu bouton-accueil">
        {t('attract.cta')}
        <img src={logoEasy} alt="easy" draggable={false} />
      </button>
    </div>
  )
}
