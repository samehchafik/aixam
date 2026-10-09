import { useRef, useState } from 'react'
import { ValidationError } from '../../api/client'
import { useApp } from '../../app-context'
import { useI18n } from '../../i18n'
import { useSession } from '../../state/session'
import { Popin, TexteLegal } from '../../components/Popin'
import { ClavierVirtuel, type ModeClavier } from '../../components/ClavierVirtuel'
import { EcranFormulaire } from './EcranFormulaire'

const FIELDS = [
  { key: 'first_name', label: 'register.firstName', type: 'text' },
  { key: 'last_name', label: 'register.lastName', type: 'text' },
  { key: 'email', label: 'register.email', type: 'email' },
  { key: 'postal_code', label: 'register.postalCode', type: 'text' },
] as const

/** Le clavier de chaque champ : lettres, adresse, ou chiffres d'abord. */
const CLAVIER: Record<string, ModeClavier> = {
  first_name: 'texte',
  last_name: 'texte',
  email: 'email',
  postal_code: 'nombre',
}

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

/**
 * Le bouton « Je passe », qui saute l'inscription, ne parait qu'avec
 * `?skip=true` dans l'adresse : pour les demonstrations et les essais, jamais
 * devant les visiteurs du salon, dont l'adresse ne le porte pas.
 */
function inscriptionFacultative(): boolean {
  return new URLSearchParams(window.location.search).get('skip') === 'true'
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
  const { api } = useApp()
  const { t } = useI18n()
  const { sessionId, inscription: values, setInscription, setVisitor, setStep, reset } = useSession()
  // Le reglement est une condition de participation, pas une option.
  const [accepte, setAccepte] = useState(false)
  const [caseOubliee, setCaseOubliee] = useState(false)
  // Les e-mails d'AIXAM, eux, sont facultatifs : la case part decochee.
  const [emailing, setEmailing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [texte, setTexte] = useState<Texte | null>(null)
  // Le champ que le clavier de la borne remplit ; aucun : clavier range.
  const [actif, setActif] = useState<string | null>(null)
  const champs = useRef<Record<string, HTMLInputElement | null>>({})

  /** Ecrit dans un champ : depuis le clavier de la borne, ou un clavier branche. */
  const ecrire = (champ: string, modifier: (valeur: string) => string) => {
    // Lu dans le magasin, pas dans le rendu : deux frappes rapides, avant que
    // la page ait repeint, partiraient sinon de la meme valeur.
    const courant = useSession.getState().inscription
    setInscription({ ...courant, [champ]: modifier(courant[champ] ?? '') })
    // Le verdict du serveur portait sur l'ancienne valeur.
    setServeur((s) => (s[champ] ? { ...s, [champ]: '' } : s))
  }
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
        consent_marketing: emailing,
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
                  ref={(el) => {
                    champs.current[field.key] = el
                  }}
                  className={valeur ? 'rempli' : ''}
                  type={field.type}
                  // Pas de clavier Windows : celui de la borne (ClavierVirtuel)
                  // le remplace -- il passait sous la fenetre. `inputMode` seul
                  // ne suffisait pas : Windows l'ouvrait quand meme, le champ
                  // perdait le focus et notre clavier clignotait. Un champ en
                  // lecture seule n'appelle aucun clavier ; il garde le focus.
                  readOnly
                  inputMode="none"
                  // Un clavier branche (poste de test) ecrit quand meme.
                  onKeyDown={(e) => {
                    if (e.ctrlKey || e.metaKey || e.altKey) return
                    if (e.key === 'Backspace') {
                      e.preventDefault()
                      ecrire(field.key, (v) => v.slice(0, -1))
                    } else if (e.key.length === 1) {
                      e.preventDefault()
                      const lettre = e.key
                      ecrire(field.key, (v) => v + lettre)
                    }
                  }}
                  onFocus={() => setActif(field.key)}
                  autoComplete="off"
                  autoCapitalize={field.type === 'text' ? 'words' : 'off'}
                  spellCheck={false}
                  value={valeur}
                  onBlur={() => {
                    setTouched((s) => ({ ...s, [field.key]: true }))
                    setActif((a) => (a === field.key ? null : a))
                  }}
                  onChange={(e) => {
                    const saisie = e.currentTarget.value
                    ecrire(field.key, () => saisie)
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

        <label className="case case-emailing">
          <input type="checkbox" checked={emailing} onChange={(e) => setEmailing(e.currentTarget.checked)} />
          <span className="case-boite" aria-hidden="true" />
          {t('register.emailing')}
        </label>

        {error && <p className="message-erreur">{error}</p>}

        <button type="submit" className="bouton bouton-blanc bouton-carte" disabled={busy}>
          {busy ? t('register.sending') : t('register.submit')}
        </button>
        <button type="button" className="lien lien-carte" onClick={reset}>
          {t('register.cancel')}
        </button>

        {/* Avec ?skip=true seulement : on saute l'inscription, sans visiteur rattache. */}
        {inscriptionFacultative() && (
          <button type="button" className="lien lien-carte" onClick={() => setStep('editor')}>
            {t('register.skip')}
          </button>
        )}
      </form>

      {actif && (
        <ClavierVirtuel
          // Une cle par champ : chacun repart sur sa disposition.
          key={actif}
          className="clavier-inscription"
          mode={CLAVIER[actif]}
          majusculeAuto={actif === 'first_name' || actif === 'last_name'}
          valeur={values[actif] ?? ''}
          onChange={(modifier) => ecrire(actif, modifier)}
          onOk={() => {
            // Champ suivant ; apres le dernier, on range le clavier.
            const i = FIELDS.findIndex((f) => f.key === actif)
            const suivant = FIELDS[i + 1]
            if (suivant) champs.current[suivant.key]?.focus()
            else champs.current[actif]?.blur()
          }}
        />
      )}

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
