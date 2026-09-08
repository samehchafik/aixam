import { useState } from 'react'
import { Anchor, Button, Checkbox, Stack, Text, TextInput, Title } from '@mantine/core'
import { useApp } from '../../app-context'
import { useI18n } from '../../i18n'
import { useSession } from '../../state/session'

const FIELDS = [
  { key: 'first_name', label: 'register.firstName', type: 'text' },
  { key: 'last_name', label: 'register.lastName', type: 'text' },
  { key: 'email', label: 'register.email', type: 'email' },
  { key: 'postal_code', label: 'register.postalCode', type: 'text' },
] as const

export function RegisterStep() {
  const { api, config } = useApp()
  const { t } = useI18n()
  const { sessionId, setVisitor, setStep } = useSession()
  const [values, setValues] = useState<Record<string, string>>({})
  const [consent, setConsent] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    setError(null)
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
      setError(e instanceof Error ? e.message : 'Erreur')
    } finally {
      setBusy(false)
    }
  }

  const complete = FIELDS.every((f) => (values[f.key] ?? '').trim().length > 1)

  return (
    <div className="form-screen">
      <Stack gap="lg" className="form-card">
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
            onChange={(e) => {
              // A lire avant setState : React 19 ne conserve pas currentTarget dans l'updater.
              const value = e.currentTarget.value
              setValues((v) => ({ ...v, [field.key]: value }))
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

        <Button className="cta" size="xl" radius="xl" disabled={!complete || busy} onClick={submit}>
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
