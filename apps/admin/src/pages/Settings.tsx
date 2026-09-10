import { useEffect, useState } from 'react'
import {
  Button, Code, Group, NumberInput, Paper, Stack, Switch, Table, Text, Title,
} from '@mantine/core'
import { api } from '../lib/api'
import { MailConfig, type MailCfg } from '../components/MailConfig'
import { RelayClients } from '../components/RelayClients'
import { SyncPanel } from '../components/SyncPanel'

type Config = {
  verification_bypass: boolean
  idle_timeout_seconds: number
  attract_interval_seconds: number
}

export function Settings() {
  const [config, setConfig] = useState<Config | null>(null)
  const [saved, setSaved] = useState(false)
  const [kiosks, setKiosks] = useState<{ id: string; name: string; token: string }[]>([])
  // La section « Clients de relais » n'a de sens que sur le back-office qui a
  // accepte ce role (RELAY_SERVER_ENABLED) ; ailleurs elle serait un ecran mort.
  const [mail, setMail] = useState<MailCfg | null>(null)

  useEffect(() => {
    api<Config>('/api/admin/settings').then(setConfig)
    api<typeof kiosks>('/api/admin/kiosks').then(setKiosks)
  }, [])

  if (!config) return <Text c="dimmed">Chargement...</Text>

  const save = async () => {
    setConfig(await api<Config>('/api/admin/settings', { method: 'PUT', body: JSON.stringify(config) }))
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <Stack gap="xl">
      <Title order={1} fz={28}>Reglages</Title>

      <Paper
        component="form"
        withBorder
        radius="md"
        p="lg"
        maw={560}
        onSubmit={(e: React.FormEvent) => {
          e.preventDefault()
          save()
        }}
      >
        <Stack gap="lg">
          <Switch
            checked={config.verification_bypass}
            onChange={(e) => setConfig({ ...config, verification_bypass: e.currentTarget.checked })}
            label="Mode degrade : ignorer la verification email"
            description="A activer si le reseau du salon tombe. Les visiteurs passent directement a la creation ; les emails partent quand la connexion revient."
          />
          <NumberInput
            label="Retour a l'accueil apres inactivite"
            suffix=" s"
            min={10}
            value={config.idle_timeout_seconds}
            onChange={(v) => setConfig({ ...config, idle_timeout_seconds: Number(v) || 0 })}
          />
          <NumberInput
            label="Vitesse du slideshow d'attente"
            suffix=" s"
            min={1}
            value={config.attract_interval_seconds}
            onChange={(v) => setConfig({ ...config, attract_interval_seconds: Number(v) || 0 })}
          />
          <Group>
            <Button type="submit" color={saved ? 'teal' : undefined}>
              {saved ? 'Enregistre' : 'Enregistrer'}
            </Button>
          </Group>
        </Stack>
      </Paper>

      <MailConfig onLoaded={setMail} />

      <SyncPanel />

      <div>
        <Title order={2} fz="lg" mb="sm">Bornes</Title>
        <Paper withBorder radius="md">
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Nom</Table.Th>
                <Table.Th>Token (a copier dans config.json)</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {kiosks.map((k) => (
                <Table.Tr key={k.id}>
                  <Table.Td fw={500}>{k.name}</Table.Td>
                  <Table.Td><Code>{k.token}</Code></Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Paper>
      </div>

      {mail?.relay_server_enabled && <RelayClients defaultQuota={mail.relay_default_daily_quota} />}
    </Stack>
  )
}
