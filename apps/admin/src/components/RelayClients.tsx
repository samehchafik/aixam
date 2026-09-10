import { useEffect, useState } from 'react'
import {
  ActionIcon, Alert, Badge, Button, Code, CopyButton, Group, NumberInput, Paper, Stack, Switch,
  Table, Text, TextInput, Title, Tooltip,
} from '@mantine/core'
import { api } from '../lib/api'

type Client = {
  id: string
  name: string
  token_prefix: string
  is_active: boolean
  daily_quota: number
  sent_today: number
  sent_total: number
  last_seen_at: string | null
  created_at: string
}

/**
 * Qui a le droit de s'appuyer sur CE back-office : faire expedier ses emails,
 * et remonter ses donnees vers lui. Un meme jeton ouvre les deux, chaque role
 * restant ferme tant qu'il n'est pas active cote serveur.
 */
export function RelayClients({ defaultQuota }: { defaultQuota: number }) {
  const [rows, setRows] = useState<Client[]>([])
  const [name, setName] = useState('')
  const [quota, setQuota] = useState(defaultQuota)
  const [fresh, setFresh] = useState<{ name: string; token: string } | null>(null)
  const [erreur, setErreur] = useState<string | null>(null)

  const load = () => api<Client[]>('/api/admin/relay-clients').then(setRows)
  useEffect(() => {
    load()
  }, [])

  const create = async () => {
    setErreur(null)
    try {
      const cree = await api<Client & { token: string }>('/api/admin/relay-clients', {
        method: 'POST',
        body: JSON.stringify({ name, daily_quota: quota }),
      })
      setFresh({ name: cree.name, token: cree.token })
      setName('')
      load()
    } catch (e) {
      setErreur((e as Error).message)
    }
  }

  const patch = async (client: Client, body: Partial<Client>) => {
    await api(`/api/admin/relay-clients/${client.id}`, { method: 'PATCH', body: JSON.stringify(body) })
    load()
  }

  const remove = async (client: Client) => {
    if (!confirm(`Révoquer définitivement « ${client.name} » ? Son jeton cessera de fonctionner.`)) return
    await api(`/api/admin/relay-clients/${client.id}`, { method: 'DELETE' })
    load()
  }

  return (
    <div>
      <Title order={2} fz="lg" mb="sm">Clients de relais</Title>
      <Stack gap="md">
        <Text c="dimmed" fz="sm" maw={720}>
          Chaque back-office autorisé à s'appuyer sur celui-ci — envoi d'e-mails, remontée des
          données — a son propre jeton, son quota et son interrupteur. Un jeton suffit : il ne se
          colle que sur des machines de confiance, et se coupe d'ici en un clic.
        </Text>

        {fresh && (
          <Alert color="aixam" variant="light" title={`Jeton de « ${fresh.name} »`} maw={720}>
            <Stack gap="xs">
              <Text fz="sm">
                Copiez-le maintenant, il ne sera plus jamais affiché (seule son empreinte est
                conservée).
              </Text>
              <Code block>{fresh.token}</Code>
              <Group>
                <CopyButton value={fresh.token}>
                  {({ copied, copy }) => (
                    <Button size="xs" variant="light" color={copied ? 'teal' : 'aixam'} onClick={copy}>
                      {copied ? 'Copié' : 'Copier'}
                    </Button>
                  )}
                </CopyButton>
                <Button size="xs" variant="subtle" onClick={() => setFresh(null)}>
                  J'ai copié le jeton
                </Button>
              </Group>
            </Stack>
          </Alert>
        )}

        {erreur && <Alert color="red" variant="light" maw={720}>{erreur}</Alert>}

        {/* Un vrai formulaire : la touche Entree cree le client. */}
        <Group
          component="form"
          align="flex-end"
          onSubmit={(e: React.FormEvent) => {
            e.preventDefault()
            if (name.trim()) create()
          }}
        >
          <TextInput
            label="Nom du back-office"
            placeholder="ex. Borne Mondial 2026"
            value={name}
            onChange={(e) => setName(e.currentTarget.value)}
            w={320}
          />
          <NumberInput
            label="Envois / jour"
            min={1}
            value={quota}
            onChange={(v) => setQuota(Number(v) || 1)}
            w={140}
          />
          <Button type="submit" disabled={!name.trim()}>Créer un client</Button>
        </Group>

        {rows.length === 0 ? (
          <Text c="dimmed" fz="sm">Aucun client. Personne ne peut s'appuyer sur ce back-office.</Text>
        ) : (
          <Paper withBorder radius="md">
            <Table.ScrollContainer minWidth={760}>
              <Table>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Nom</Table.Th>
                    <Table.Th>Préfixe</Table.Th>
                    <Table.Th>Aujourd'hui</Table.Th>
                    <Table.Th>Total</Table.Th>
                    <Table.Th>Dernière activité</Table.Th>
                    <Table.Th>État</Table.Th>
                    <Table.Th />
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {rows.map((row) => (
                    <Table.Tr key={row.id} opacity={row.is_active ? 1 : 0.55}>
                      <Table.Td fw={500}>{row.name}</Table.Td>
                      <Table.Td><Code>{row.token_prefix}</Code></Table.Td>
                      <Table.Td>
                        <Badge variant="light" color={row.sent_today >= row.daily_quota ? 'red' : 'gray'}>
                          {row.sent_today} / {row.daily_quota}
                        </Badge>
                      </Table.Td>
                      <Table.Td>{row.sent_total}</Table.Td>
                      <Table.Td c="dimmed" fz="sm">
                        {row.last_seen_at ? new Date(row.last_seen_at).toLocaleString('fr-FR') : 'jamais'}
                      </Table.Td>
                      <Table.Td>
                        <Switch
                          size="sm"
                          checked={row.is_active}
                          onChange={(e) => patch(row, { is_active: e.currentTarget.checked })}
                          label={row.is_active ? 'actif' : 'coupé'}
                        />
                      </Table.Td>
                      <Table.Td>
                        <Tooltip label="Révoquer" withArrow>
                          <ActionIcon variant="subtle" color="red" onClick={() => remove(row)} aria-label="Révoquer">
                            ×
                          </ActionIcon>
                        </Tooltip>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          </Paper>
        )}
      </Stack>
    </div>
  )
}
