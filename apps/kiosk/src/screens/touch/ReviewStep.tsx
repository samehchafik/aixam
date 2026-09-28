import { useState } from 'react'
import { useApp } from '../../app-context'
import { useI18n } from '../../i18n'
import { useSession } from '../../state/session'
import { Ribbon } from '../../components/chrome/Ribbon'
import { PlancheEnDirect } from '../../components/PlancheEnDirect'
import { PlancheEnGrand } from '../../components/PlancheEnGrand'
import logoBasDroite from '../../assets/logo-bas-droite.png'

/**
 * Ecran 7 : le skin pose sur la voiture, avant l'envoi. Rien n'est enregistre
 * tant que le visiteur n'a pas valide ; « Retour » le ramene a sa creation,
 * intacte.
 */
export function ReviewStep() {
  const { api, bus } = useApp()
  const { t } = useI18n()
  const { layers, sessionId, visitorId, setRenderUrl, setStep } = useSession()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const valider = async () => {
    setBusy(true)
    setError(null)
    try {
      const res = await api.saveDesign({ session_id: sessionId, visitor_id: visitorId, layers })
      const url = res.render_url ? `${api.base}${res.render_url}` : null
      setRenderUrl(url)
      bus.send({ type: 'finished', renderUrl: url })
      setStep('done')
    } catch {
      setError(t('review.submitError'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="ecran">
      <PlancheEnDirect layers={layers} />
      <img className="logo-bas-droite" src={logoBasDroite} alt="" draggable={false} />
      <Ribbon modele="editeur" />
      <PlancheEnGrand layers={layers} />

      {error && <p className="message-erreur revue-erreur">{error}</p>}
      <button type="button" className="bouton bouton-bleu bouton-valider" disabled={busy} onClick={valider}>
        {busy ? t('review.sending') : t('review.submit')}
      </button>
      <button type="button" className="lien lien-retour" disabled={busy} onClick={() => setStep('editor')}>
        {t('review.back')}
      </button>
    </div>
  )
}
