import { Button, Stack, Text, Title } from '@mantine/core'
import { useI18n } from '../../i18n'
import { useSession } from '../../state/session'

export function DoneStep() {
  const { t } = useI18n()
  const { firstName, reset } = useSession()

  return (
    <div className="form-screen">
      <Stack gap="xl" className="form-card" align="center" style={{ textAlign: 'center' }}>
        <Title order={1} className="form-title">{t('done.title', { firstName })}</Title>
        <Text size="xl" c="dimmed">{t('done.lead')}</Text>
        <Text size="xl">{t('done.share')}</Text>
        <Button className="cta" size="xl" radius="xl" onClick={reset}>{t('done.finish')}</Button>
      </Stack>
    </div>
  )
}
