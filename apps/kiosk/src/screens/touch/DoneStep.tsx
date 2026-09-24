import { useI18n } from '../../i18n'
import { useSession } from '../../state/session'
import { Fond } from '../../components/Stage16x9'
import fondMerci from '../../assets/fond-merci.avif'

/**
 * Ecran 8 : le remerciement. « Creer un nouveau skin » repart de l'accueil,
 * pas de l'editeur : le prochain a toucher l'ecran est souvent quelqu'un
 * d'autre, et sa creation partirait sinon a l'adresse du precedent.
 */
export function DoneStep() {
  const { t, rich } = useI18n()
  const reset = useSession((s) => s.reset)

  return (
    <div className="ecran">
      <Fond src={fondMerci} />
      {/* @aixam_officiel est un decor, pas un lien : il n'y a rien a ouvrir
          sur une borne. */}
      <p className="texte-ecran texte-merci">
        {rich('done.text', { compte: <span className="accent">{t('done.account')}</span> })}
      </p>
      <button type="button" className="bouton bouton-bleu bouton-merci" onClick={reset}>
        {t('done.restart')}
      </button>
    </div>
  )
}
