import { useEffect, useState } from 'react'
import {
  ActionIcon, Badge, Button, Group, Pagination, Paper, Stack, Table, Text, TextInput, Title, Tooltip,
} from '@mantine/core'
import { api, telecharger } from '../lib/api'

type Row = {
  id: string
  first_name: string
  last_name: string
  email: string
  postal_code: string
  email_verified_at: string | null
  consent_marketing: boolean
  created_at: string
}

const PAR_PAGE = 25

export function Visitors() {
  const [rows, setRows] = useState<Row[]>([])
  const [total, setTotal] = useState(0)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [erreur, setErreur] = useState<string | null>(null)

  const load = () => {
    const q = new URLSearchParams({
      limit: String(PAR_PAGE),
      offset: String((page - 1) * PAR_PAGE),
      search,
    })
    return api<{ total: number; items: Row[] }>(`/api/admin/visitors?${q}`).then((res) => {
      setRows(res.items)
      setTotal(res.total)
    })
  }

  // La recherche ramene a la premiere page : rester en page 4 d'un resultat
  // qui n'en compte plus qu'une afficherait un tableau vide sans raison.
  useEffect(() => {
    setPage(1)
  }, [search])

  useEffect(() => {
    const id = setTimeout(load, 250)
    return () => clearTimeout(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, page])

  const supprimer = async (row: Row) => {
    if (!confirm(`Supprimer définitivement ${row.first_name} ${row.last_name} (demande RGPD) ?\n\nSes créations sont conservées, mais anonymisées.`)) return
    await api(`/api/admin/visitors/${row.id}`, { method: 'DELETE' })
    load()
  }

  const pages = Math.max(1, Math.ceil(total / PAR_PAGE))

  return (
    <Stack gap="md">
      <Group justify="space-between" align="baseline">
        <Title order={1} fz={28}>
          Visiteurs <Text span c="dimmed" fz={28} fw={400}>({total})</Text>
        </Title>
      </Group>

      <Group>
        <TextInput
          placeholder="Rechercher un nom ou un e-mail"
          value={search}
          onChange={(e) => setSearch(e.currentTarget.value)}
          w={280}
          aria-label="Rechercher un visiteur"
        />
        <Button
          variant="light"
          onClick={() =>
            telecharger('/api/admin/visitors.csv?consented_only=true', 'visiteurs.csv')
              .catch((e) => setErreur(e.message))
          }
        >
          Export CSV (opt-in)
        </Button>
      </Group>
      {erreur && <Text c="red" fz="sm">Export impossible : {erreur}</Text>}

      <Paper withBorder radius="md">
        <Table.ScrollContainer minWidth={720}>
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Nom</Table.Th>
                <Table.Th>E-mail</Table.Th>
                <Table.Th>CP</Table.Th>
                <Table.Th>Vérifié</Table.Th>
                <Table.Th>Opt-in</Table.Th>
                <Table.Th>Date</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rows.map((row) => (
                <Table.Tr key={row.id}>
                  <Table.Td fw={500}>{row.first_name} {row.last_name}</Table.Td>
                  <Table.Td c="dimmed">{row.email}</Table.Td>
                  <Table.Td>{row.postal_code}</Table.Td>
                  <Table.Td>
                    {row.email_verified_at
                      ? <Badge color="teal" variant="light">oui</Badge>
                      : <Text c="dimmed">—</Text>}
                  </Table.Td>
                  <Table.Td>
                    {row.consent_marketing
                      ? <Badge color="blue" variant="light">oui</Badge>
                      : <Text c="dimmed">—</Text>}
                  </Table.Td>
                  <Table.Td c="dimmed" fz="sm">
                    {new Date(row.created_at).toLocaleString('fr-FR')}
                  </Table.Td>
                  <Table.Td>
                    <Tooltip label="Supprimer (RGPD)" withArrow>
                      <ActionIcon variant="subtle" color="red" onClick={() => supprimer(row)} aria-label="Supprimer">
                        ×
                      </ActionIcon>
                    </Tooltip>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
        {rows.length === 0 && (
          <Text c="dimmed" fz="sm" p="md">
            {search ? 'Aucun visiteur ne correspond.' : 'Aucun visiteur pour le moment.'}
          </Text>
        )}
      </Paper>

      {pages > 1 && (
        <Group justify="space-between">
          <Text c="dimmed" fz="sm">Page {page} sur {pages}</Text>
          <Pagination total={pages} value={page} onChange={setPage} size="sm" withEdges />
        </Group>
      )}
    </Stack>
  )
}
