import { useState } from 'react'
import { Anchor, Button, Checkbox, Stack, Text, TextInput, Title } from '@mantine/core'
import { ValidationError } from '../../api/client'
import { useApp } from '../../app-context'
import { useI18n } from '../../i18n'
import { useSession } from '../../state/session'

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

export function RegisterStep() {
  const { api, config } = useApp()
  const { t } = useI18n()
  const { sessionId, setVisitor, setStep } = useSession()
  const [values, setValues] = useState<Record<string, string>>({})
  const [consent, setConsent] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
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
    if (FIELDS.some((f) => erreurs[f.key])) {
      setTouched(Object.fromEntries(FIELDS.map((f) => [f.key, true])))
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
        consent_marketing: consent,
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

  const complete = FIELDS.every((f) => !erreurs[f.key])

  return (
    <div className="form-screen">
      {/* Un vrai formulaire : sur un ecran tactile, la touche de validation du
          clavier virtuel envoie alors la saisie. Sans cela elle est inerte, et
          le visiteur doit viser le bouton -- clavier ouvert par-dessus. */}
      <Stack
        component="form"
        gap="lg"
        className="form-card"
        onSubmit={(e: React.FormEvent) => {
          e.preventDefault()
          submit()
        }}
      >
        <div>
          <Title order={1} className="form-title">{t('register.title')}</Title>
          <Text c="dimmed" size="lg">{t('register.lead')}</Text>
        </div>

        {FIELDS.map((field) => (
          <TextInput
            key={field.key}
            size="xl"
            radius="md"
            label={t(field.label)}
            type={field.type}
            inputMode={field.key === 'postal_code' ? 'numeric' : undefined}
            autoComplete="off"
            value={values[field.key] ?? ''}
            error={messageDuChamp(field.key)}
            onBlur={() => setTouched((s) => ({ ...s, [field.key]: true }))}
            onChange={(e) => {
              // A lire avant setState : React 19 ne conserve pas currentTarget dans l'updater.
              const value = e.currentTarget.value
              setValues((v) => ({ ...v, [field.key]: value }))
              // Le verdict du serveur portait sur l'ancienne valeur.
              setServeur((s) => (s[field.key] ? { ...s, [field.key]: '' } : s))
            }}
          />
        ))}

        <Checkbox
          size="md"
          checked={consent}
          onChange={(e) => setConsent(e.currentTarget.checked)}
          label={<Text size="sm" c="dimmed">{t('register.consent')}</Text>}
        />

        {error && <Text c="red.4">{error}</Text>}

        <Button type="submit" className="cta" size="xl" radius="xl" disabled={!complete || busy}>
          {busy ? t('register.sending') : t('register.submit')}
        </Button>

        {/* Mode demo (config.json) : on saute l'inscription, sans visiteur rattache. */}
        {config.demoMode && (
          <Anchor component="button" type="button" className="restart" ta="center" onClick={() => setStep('editor')}>
            {t('register.skip')}
          </Anchor>
        )}
      </Stack>
    </div>
  )
}
