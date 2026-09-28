import { useState } from 'react'
import { useApp } from '../../app-context'
import { useI18n } from '../../i18n'
import { useSession } from '../../state/session'
import { Ribbon } from '../../components/chrome/Ribbon'
import { SkinCanvas } from '../../components/SkinCanvas'
import { SkinMockup } from '../../components/SkinMockup'
import logoBasDroite from '../../assets/logo-bas-droite.png'

/**
 * La planche du bas, relevee sur l'ecran 7 : la meme que celle de l'editeur,
 * un peu plus large et au contour un peu plus epais, pour la detacher de la
 * photo.
 */
const PLANCHE = { x: 103, y: 747, largeur: 1714, contour: 4 }

/**
 * Ecran 7 : le skin pose sur la voiture, avant l'envoi. Rien n'est enregistre
 * tant que le visiteur n'a pas valide ; « Retour » le ramene a sa creation,
 * intacte.
 */
export function ReviewStep() {
  const { api, bus } = useApp()
  const { t } = useI18n()
  const { catalog, layers, sessionId, visitorId, setRenderUrl, setStep } = useSession()
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
