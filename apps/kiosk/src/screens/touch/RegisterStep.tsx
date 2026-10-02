import { useState } from 'react'
import { ValidationError } from '../../api/client'
import { useApp } from '../../app-context'
import { useI18n } from '../../i18n'
import { useSession } from '../../state/session'
import { Popin, TexteLegal } from '../../components/Popin'
import { EcranFormulaire } from './EcranFormulaire'

const FIELDS = [
  { key: 'first_name', label: 'register.firstName', type: 'text' },
  { key: 'last_name', label: 'register.lastName', type: 'text' },
  { key: 'email', label: 'register.email', type: 'email' },
  { key: 'postal_code', label: 'register.postalCode', type: 'text' },
] as const

// Exige un point dans le domaine : c'est ce qui attrape le « gmail;com » tape
// au pouce sur un clavier tactile, ou le point-virgule est voisin du point.
const EMAIL = /^[^\s@]+@[^\s@.]+(\.[^\s@.]+)+$/
// Volontairement tolerant : le Mondial recoit des visiteurs etrangers, dont
// les codes postaux contiennent des lettres et des espaces.
const CODE_POSTAL = /^[A-Za-z0-9][A-Za-z0-9 -]{3,9}$/

// Notre message pour chaque champ que le serveur peut refuser. Il repond en
// anglais et en jargon ; le visiteur, lui, lit sa langue.
const CLES_ERREUR: Record<string, string> = {
  first_name: 'register.errors.name',
  last_name: 'register.errors.name',
  email: 'register.errors.email',
  postal_code: 'register.errors.postalCode',
}

/** Rend la cle du message d'erreur, ou null si la valeur convient. */
function valider(champ: string, valeur: string): string | null {
  const v = valeur.trim()
  if (!v) return 'register.errors.required'
  if (champ === 'email') return EMAIL.test(v) ? null : 'register.errors.email'
  if (champ === 'postal_code') return CODE_POSTAL.test(v) ? null : 'register.errors.postalCode'
  return v.length >= 2 ? null : 'register.errors.name'
}

/** Le texte que la case du reglement ouvre dans la popin. */
type Texte = 'rules'

/** Le fichier de chaque texte, dans `public/legal/`. */
const FICHIERS: Record<Texte, string> = { rules: 'reglement' }

/**
 * Ecran 2 : le formulaire, sur la carte bleue.
 *
 * Le bouton reste actif meme formulaire vide, comme le dessine le studio : le
 * visiteur qui appuie trop tot voit ce qui manque (ecran 2c), plutot qu'un
 * bouton grise dont il ne comprend pas le refus.
 */
export function RegisterStep() {
  const { api, config } = useApp()
  const { t } = useI18n()
  const { sessionId, inscription: values, setInscription, setVisitor, setStep, reset } = useSession()
  // Le reglement est une condition de participation, pas une option.
  const [accepte, setAccepte] = useState(false)
  const [caseOubliee, setCaseOubliee] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [texte, setTexte] = useState<Texte | null>(null)
  // Un champ ne signale sa faute qu'une fois quitte : corriger sous les doigts
  // du visiteur pendant qu'il tape serait plus penible qu'utile.
  const [touched, setTouched] = useState<Record<string, boolean>>({})
  // Fautes renvoyees par l'API, rangees par champ. Elles priment sur la
  // validation locale : le serveur en sait plus (domaine reserve, par exemple).
  const [serveur, setServeur] = useState<Record<string, string>>({})

  const erreurs = Object.fromEntries(
    FIELDS.map((f) => [f.key, valider(f.key, values[f.key] ?? '')]),
  ) as Record<string, string | null>

  /** Ce qu'on montre sous un champ : rien tant qu'il n'a pas ete quitte. */
  const messageDuChamp = (champ: string): string | undefined => {
    if (serveur[champ]) return serveur[champ]
    return touched[champ] && erreurs[champ] ? t(erreurs[champ]!) : undefined
  }

  const submit = async () => {
    // Le serveur revalide de toute facon ; le faire ici evite au visiteur un
    // aller-retour reseau pour un point-virgule.
    const incomplet = FIELDS.some((f) => erreurs[f.key])
    if (incomplet || !accepte) {
      setTouched(Object.fromEntries(FIELDS.map((f) => [f.key, true])))
      setCaseOubliee(!accepte)
      return
    }
    setError(null)
    setServeur({})
    setBusy(true)
    try {
      const res = await api.register({
        first_name: values.first_name ?? '',
        last_name: values.last_name ?? '',
        email: values.email ?? '',
        postal_code: values.postal_code ?? '',
        session_id: sessionId,
      })
      setVisitor(res.visitor_id, values.first_name ?? '')
      api.track('register_submitted', {}, sessionId)
      setStep(res.verification_required ? 'verify' : 'editor')
    } catch (e) {
      if (e instanceof ValidationError) {
        // Le serveur repond en anglais et en jargon. On garde le champ qu'il
        // designe, mais on affiche notre propre message, traduit.
        const traduits = Object.fromEntries(
          Object.entries(e.fields).map(([champ, brut]) => [
            champ,
            CLES_ERREUR[champ] ? t(CLES_ERREUR[champ]) : brut,
          ]),
        )
        setServeur(traduits)
        setTouched((s) => ({ ...s, ...Object.fromEntries(Object.keys(traduits).map((k) => [k, true])) }))
      } else {
        setError(e instanceof Error ? e.message : 'Erreur')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <EcranFormulaire>
      {/* Un vrai formulaire : sur un ecran tactile, la touche de validation du
          clavier virtuel envoie alors la saisie. Sans cela elle est inerte, et
          le visiteur doit viser le bouton -- clavier ouvert par-dessus. */}
      <form
        className="carte carte-inscription"
        noValidate
        onSubmit={(e) => {
          e.preventDefault()
          submit()
        }}
      >
        {FIELDS.map((field) => {
          const message = messageDuChamp(field.key)
          const valeur = values[field.key] ?? ''
          return (
            <div key={field.key} className={`champ ${message ? 'en-erreur' : ''}`}>
              <label htmlFor={`champ-${field.key}`}>{t(field.label)}*</label>
              <div>
                <input
                  id={`champ-${field.key}`}
                  className={valeur ? 'rempli' : ''}
                  type={field.type}
                  inputMode={field.type === 'email' ? 'email' : undefined}
                  autoComplete="off"
                  autoCapitalize={field.type === 'text' ? 'words' : 'off'}
                  spellCheck={false}
                  value={valeur}
                  onBlur={() => setTouched((s) => ({ ...s, [field.key]: true }))}
                  onChange={(e) => {
                    setInscription({ ...values, [field.key]: e.currentTarget.value })
                    // Le verdict du serveur portait sur l'ancienne valeur.
                    setServeur((s) => (s[field.key] ? { ...s, [field.key]: '' } : s))
                  }}
                />
                {message && <p className="message-erreur">{message}</p>}
              </div>
            </div>
          )
        })}

        <p className="obligatoires">{t('register.required')}</p>
        <div className="mentions">
          {t('register.legal').split('\n').map((paragraphe, i) => (
            <p key={i}>{paragraphe}</p>
          ))}
        </div>

        <label className={`case ${caseOubliee && !accepte ? 'en-erreur' : ''}`}>
          <input
            type="checkbox"
            checked={accepte}
            onChange={(e) => {
              setCaseOubliee(false)
              // Cocher, c'est accepter le reglement : on l'ouvre, et la case ne
              // se coche qu'avec son bouton, une fois le texte lu jusqu'au
              // bout. Decocher reste direct.
              if (e.currentTarget.checked) setTexte('rules')
              else setAccepte(false)
            }}
          />
          <span className="case-boite" aria-hidden="true" />
          {t('register.rules')}
        </label>

        {error && <p className="message-erreur">{error}</p>}

        <button type="submit" className="bouton bouton-blanc bouton-carte" disabled={busy}>
          {busy ? t('register.sending') : t('register.submit')}
        </button>
        <button type="button" className="lien lien-carte" onClick={reset}>
          {t('register.cancel')}
        </button>

        {/* Mode demo (config.json) : on saute l'inscription, sans visiteur rattache. */}
        {config.demoMode && (
          <button type="button" className="lien lien-carte" onClick={() => setStep('editor')}>
            {t('register.skip')}
          </button>
        )}
      </form>

      {texte && (
        <Popin
          titre={t(`legal.${texte}.title`)}
          onClose={() => setTexte(null)}
          validation={
            texte === 'rules'
              ? {
                  libelle: t('legal.rules.accept'),
                  aide: t('legal.rules.readFirst'),
                  onValider: () => {
                    setAccepte(true)
                    setCaseOubliee(false)
                    setTexte(null)
                  },
                }
              : undefined
          }
        >
          <TexteLegal nom={FICHIERS[texte]} />
        </Popin>
      )}
    </EcranFormulaire>
  )
}
