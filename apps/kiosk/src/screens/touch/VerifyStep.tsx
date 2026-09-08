import { useState } from 'react'
import { Button, Center, PinInput, Stack, Text, Title } from '@mantine/core'
import { useApp } from '../../app-context'
import { useI18n } from '../../i18n'
import { useSession } from '../../state/session'

export function VerifyStep() {
  const { api } = useApp()
  const { t } = useI18n()
  const { visitorId, sessionId, setStep } = useSession()
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (!visitorId) return
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
    <div className="form-screen">
      <Stack gap="xl" className="form-card" align="center">
        <div style={{ textAlign: 'center' }}>
          <Title order={1} className="form-title">{t('verify.title')}</Title>
          <Text c="dimmed" size="lg">{t('verify.lead')}</Text>
        </div>

        <Center>
          <PinInput length={6} size="xl" type="number" inputMode="numeric" value={code} onChange={setCode} />
        </Center>

        {error && <Text c="red.4">{error}</Text>}

        <Button className="cta" size="xl" radius="xl" disabled={code.length < 6 || busy} onClick={submit}>
          {busy ? t('verify.checking') : t('verify.submit')}
        </Button>
      </Stack>
    </div>
  )
}
