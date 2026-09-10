import { useEffect, useState } from 'react'
import {
  Alert, Button, Group, Paper, PasswordInput, Select, Stack, Text, TextInput, Title,
} from '@mantine/core'
import { api } from '../lib/api'

export type MailCfg = {
  transport: 'smtp' | 'brevo' | 'relay'
  transports: string[]
  mail_from: string
  mail_from_name: string
  smtp_host: string
  smtp_port: number
  smtp_configured: boolean
  brevo_configured: boolean
  relay_url: string
  relay_token_set: boolean
  relay_server_enabled: boolean
  relay_default_daily_quota: number
  mail_reply_to: string
  from_domain: string
  smtp_domain: string
  domains_aligned: boolean
}

const TRANSPORTS = [
  { value: 'smtp', label: 'SMTP — boîte OVH ou relais Brevo' },
  { value: 'brevo', label: 'Brevo — API HTTP' },
  { value: 'relay', label: 'Relais — via un autre back-office AIXAM' },
]

const EXPLIQUE: Record<MailCfg['transport'], string> = {
  smtp: "La boîte du serveur OVH, ou le relais SMTP de Brevo. Demande que le port SMTP sorte du réseau.",
  brevo: "L'API HTTP de Brevo. Tout passe en 443 : à choisir si le réseau du salon filtre le port 587.",
  relay: "On n'expédie pas d'ici. Les e-mails sont confiés à un autre back-office AIXAM, qui a la configuration d'envoi et la réputation auprès des messageries.",
}

/** Par ou sortent les emails de CE back-office. */
export function MailConfig({ onLoaded }: { onLoaded?: (cfg: MailCfg) => void }) {
  const [cfg, setCfg] = useState<MailCfg | null>(null)
  const [token, setToken] = useState('')
  const [saved, setSaved] = useState(false)
  const [probe, setProbe] = useState<string | null>(null)
  const [testTo, setTestTo] = useState('')
  const [testMsg, setTestMsg] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api<MailCfg>('/api/admin/mail').then((next) => {
      setCfg(next)
      onLoaded?.(next)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (!cfg) return <Text c="dimmed">Chargement...</Text>

  const save = async () => {
    setError(null)
    try {
      const next = await api<MailCfg>('/api/admin/mail', {
        method: 'PUT',
        body: JSON.stringify({
          transport: cfg.transport,
          relay_url: cfg.relay_url,
          // Champ vide = « ne touche pas » : le jeton n'est jamais reaffiche,
          // le laisser vide ne doit pas l'effacer.
          ...(token ? { relay_token: token } : {}),
        }),
      })
      setCfg(next)
      setToken('')
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const testRelay = async () => {
    setProbe('Test en cours...')
    const res = await api<{ ok: boolean; error?: string; remote?: Record<string, unknown> }>(
      '/api/admin/mail/test-relay', { method: 'POST' },
    )
    setProbe(res.ok
      ? `Liaison établie — enregistré sous « ${res.remote!.client} », expédié depuis ${res.remote!.mail_from}, ${res.remote!.remaining_today} envoi(s) restant(s) aujourd'hui.`
      : `Échec : ${res.error}`)
  }

  const sendTest = async () => {
    setTestMsg(null)
    try {
      await api('/api/admin/mail/test-send', { method: 'POST', body: JSON.stringify({ to: testTo }) })
      setTestMsg(`E-mail de test mis en file pour ${testTo}. Suivez-le dans « E-mails ».`)
      setTestTo('')
    } catch (e) {
      setTestMsg(`Échec : ${(e as Error).message}`)
    }
  }

  const incomplet =
    (cfg.transport === 'smtp' && !cfg.smtp_configured) ||
    (cfg.transport === 'brevo' && !cfg.brevo_configured) ||
    (cfg.transport === 'relay' && (!cfg.relay_url || !cfg.relay_token_set))

  return (
    <div>
      <Title order={2} fz="lg" mb="sm">Envoi des e-mails</Title>
      <Stack gap="md" maw={560}>
        <Paper
          component="form"
          withBorder
          radius="md"
          p="lg"
          onSubmit={(e: React.FormEvent) => {
            e.preventDefault()
            save()
          }}
        >
          <Stack gap="md">
            <Select
              label="Par où sortent les e-mails"
              description={EXPLIQUE[cfg.transport]}
              data={TRANSPORTS}
              value={cfg.transport}
              onChange={(v) => setCfg({ ...cfg, transport: (v as MailCfg['transport']) ?? 'smtp' })}
            />

            {cfg.transport === 'smtp' && (
              <Text c="dimmed" fz="sm">
                {cfg.smtp_configured
                  ? `Serveur : ${cfg.smtp_host}:${cfg.smtp_port} — expéditeur ${cfg.mail_from}`
                  : 'SMTP_HOST n’est pas renseigné dans le .env : aucun e-mail ne partira.'}
              </Text>
            )}

            {cfg.transport === 'smtp' && cfg.smtp_configured && !cfg.domains_aligned && (
              <Alert color="orange" variant="light" title="Expéditeur non aligné">
                L’expéditeur est en <b>@{cfg.from_domain}</b> mais la boîte authentifiée en{' '}
                <b>@{cfg.smtp_domain}</b>. SPF et DKIM signeront pour le second : si{' '}
                {cfg.from_domain} publie un DMARC en <b>p=reject</b>, l’e-mail sera{' '}
                <b>rejeté</b>, pas classé en indésirable.
              </Alert>
            )}

            {cfg.transport === 'brevo' && (
              <Text c="dimmed" fz="sm">
                {cfg.brevo_configured
                  ? `Clé API en place — expéditeur ${cfg.mail_from}`
                  : 'BREVO_API_KEY n’est pas renseignée dans le .env : aucun e-mail ne partira.'}
              </Text>
            )}

            {cfg.transport === 'relay' && (
              <>
                <TextInput
                  label="Adresse du back-office distant"
                  description="En https : le jeton voyagerait en clair sur le réseau du salon autrement."
                  placeholder="https://bo.aixam.fr"
                  value={cfg.relay_url}
                  onChange={(e) => setCfg({ ...cfg, relay_url: e.currentTarget.value })}
                />
                <PasswordInput
                  label="Jeton de relais"
                  description="Généré dans « Clients de relais » du back-office distant. Il n'y est affiché qu'une fois."
                  placeholder={cfg.relay_token_set ? 'Jeton en place — laisser vide pour le garder' : 'axr_...'}
                  autoComplete="off"
                  value={token}
                  onChange={(e) => setToken(e.currentTarget.value)}
                />
              </>
            )}

            {incomplet && (
              <Alert color="orange" variant="light">
                Configuration incomplète : les e-mails s'empileront dans la file sans partir.
              </Alert>
            )}
            {error && <Alert color="red" variant="light">{error}</Alert>}

            <Group>
              <Button type="submit" color={saved ? 'teal' : undefined}>
                {saved ? 'Enregistré' : 'Enregistrer'}
              </Button>
              {cfg.transport === 'relay' && (
                // type=button : dans un formulaire, le defaut est submit.
                <Button type="button" variant="subtle" onClick={testRelay}>Tester la liaison</Button>
              )}
            </Group>
            {probe && <Text c="dimmed" fz="sm">{probe}</Text>}
          </Stack>
        </Paper>

        <Paper
          component="form"
          withBorder
          radius="md"
          p="lg"
          onSubmit={(e: React.FormEvent) => {
            e.preventDefault()
            if (testTo) sendTest()
          }}
        >
          <Stack gap="sm">
            <TextInput
              label="Envoyer un e-mail de test"
              description="Passe par la file et le worker : c'est la chaîne complète qui est validée, pas seulement la configuration."
              type="email"
              autoComplete="email"
              placeholder="vous@exemple.fr"
              value={testTo}
              onChange={(e) => setTestTo(e.currentTarget.value)}
            />
            {!cfg.mail_reply_to && cfg.transport === 'smtp' && cfg.smtp_configured && (
              <Text c="dimmed" fz="xs">
                Aucune adresse de réponse (MAIL_REPLY_TO) : un expéditeur qui n’accepte pas de
                réponse pèse un peu dans le classement en indésirable.
              </Text>
            )}
            <Group>
              <Button type="submit" variant="light" disabled={!testTo}>Envoyer</Button>
            </Group>
            {testMsg && <Text c="dimmed" fz="sm">{testMsg}</Text>}
          </Stack>
        </Paper>
      </Stack>
    </div>
  )
}
