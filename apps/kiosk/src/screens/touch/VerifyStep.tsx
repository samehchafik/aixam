import { useState } from 'react'
import { PinInput } from '@mantine/core'
import { useApp } from '../../app-context'
import { useI18n } from '../../i18n'
import { useSession } from '../../state/session'
import { EcranFormulaire } from './EcranFormulaire'

/** Longueur du code quand l'API ne la donne pas : celle d'avant les cinq cases. */
const LONGUEUR_PAR_DEFAUT = 6

/** Ecran 3 : le code recu par email, une case par chiffre. */
export function VerifyStep() {
  const { api, settings } = useApp()
  const { t } = useI18n()
  const { visitorId, sessionId, setStep } = useSession()
  const longueur = settings.verification_code_length ?? LONGUEUR_PAR_DEFAUT
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (!visitorId || code.length < longueur) return
    setBusy(true)
    setError(null)
    try {
      const res = await api.verify(visitorId, code)
      if (res.verified) {
        api.track('verified', {}, sessionId)
        setStep('editor')
      } else {
        setError(t('verify.wrong', { remaining: res.remaining_attempts }))
        setCode('')
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erreur')
    } finally {
      setBusy(false)
    }
  }

  return (
    <EcranFormulaire>
      <p className="texte-ecran texte-derniere-etape">{t('verify.aside')}</p>
      <form
        className="carte carte-code"
        onSubmit={(e) => {
          e.preventDefault()
          submit()
        }}
        // Les cases du code gardent la touche Entree pour elles : sans ceci,
        // la validation du clavier tactile ne faisait rien.
        onKeyDown={(e) => {
          if (e.key === 'Enter' && e.target instanceof HTMLInputElement) {
            e.preventDefault()
            submit()
          }
        }}
      >
        <p className="carte-titre">{t('verify.title')}</p>
        <PinInput
          unstyled
          classNames={{ root: 'code', input: 'code-case' }}
          length={longueur}
          type="number"
          inputMode="numeric"
          // Une espace, pas rien : `:placeholder-shown` distingue alors une
          // case vide (bleu pale) d'une case remplie (blanche).
          placeholder=" "
          oneTimeCode
          autoFocus
          value={code}
          onChange={setCode}
        />
        {error && <p className="message-erreur">{error}</p>}
        <button type="submit" className="bouton bouton-blanc bouton-code" disabled={code.length < longueur || busy}>
          {busy ? t('verify.checking') : t('verify.submit')}
        </button>
        <button type="button" className="lien lien-carte" onClick={() => setStep('register')}>
          {t('verify.back')}
        </button>
      </form>
    </EcranFormulaire>
  )
}
