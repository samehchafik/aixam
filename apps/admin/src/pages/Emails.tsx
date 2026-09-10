import { useEffect, useState } from 'react'
import { Badge, Button, Group, Paper, Stack, Table, Text, Title } from '@mantine/core'
import { api } from '../lib/api'

type Row = {
  id: string
  to: string
  subject: string
  status: string
  attempts: number
  last_error: string | null
  created_at: string
  sent_at: string | null
}

const COULEURS: Record<string, string> = {
  pending: 'yellow',
  sending: 'blue',
  sent: 'teal',
  failed: 'red',
}

export function Emails() {
  const [rows, setRows] = useState<Row[]>([])
  const [busy, setBusy] = useState(false)

  const load = () => api<Row[]>('/api/admin/emails').then(setRows)

  useEffect(() => {
    load()
    const id = setInterval(load, 10_000)
    return () => clearInterval(id)
  }, [])

  const echecs = rows.filter((r) => r.status === 'failed').length

  return (
    <Stack gap="md">
      <Title order={1} fz={28}>File d'envoi</Title>

      <Group>
        <Button
          variant="light"
          loading={busy}
          disabled={echecs === 0}
          onClick={async () => {
            setBusy(true)
            try {
              await api('/api/admin/emails/retry-failed', { method: 'POST' })
              await load()
            } finally {
              setBusy(false)
            }
          }}
        >
          Relancer les échecs{echecs > 0 ? ` (${echecs})` : ''}
        </Button>
        <Text c="dimmed" fz="sm">Actualisé toutes les 10 secondes.</Text>
      </Group>

      <Paper withBorder radius="md">
        <Table.ScrollContainer minWidth={760}>
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Destinataire</Table.Th>
                <Table.Th>Objet</Table.Th>
                <Table.Th>Statut</Table.Th>
                <Table.Th>Essais</Table.Th>
                <Table.Th>Erreur</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rows.map((row) => (
                <Table.Tr key={row.id}>
                  <Table.Td fw={500}>{row.to}</Table.Td>
                  <Table.Td c="dimmed">{row.subject}</Table.Td>
                  <Table.Td>
                    <Badge color={COULEURS[row.status] ?? 'gray'} variant="light">{row.status}</Badge>
                  </Table.Td>
                  <Table.Td>{row.attempts}</Table.Td>
                  <Table.Td c="dimmed" fz="sm" style={{ maxWidth: 320 }}>
                    {row.last_error ?? '—'}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
        {rows.length === 0 && (
          <Text c="dimmed" fz="sm" p="md">Aucun e-mail en file.</Text>
        )}
      </Paper>
    </Stack>
  )
}
