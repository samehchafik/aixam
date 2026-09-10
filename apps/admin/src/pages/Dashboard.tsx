import { useEffect, useState } from 'react'
import { Card, Group, Paper, SimpleGrid, Stack, Text, Title, Tooltip } from '@mantine/core'
import { api, type Stats } from '../lib/api'

type Point = { bucket: string; name: string; count: number }

export function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [timeline, setTimeline] = useState<Point[]>([])

  useEffect(() => {
    const load = () => {
      api<Stats>('/api/admin/stats').then(setStats).catch(() => {})
      api<Point[]>('/api/admin/timeline?hours=24').then(setTimeline).catch(() => {})
    }
    load()
    const id = setInterval(load, 15_000)
    return () => clearInterval(id)
  }, [])

  if (!stats) return <Text c="dimmed">Chargement...</Text>

  const cartes = [
    { label: 'Visiteurs inscrits', value: stats.visitors_total },
    { label: 'E-mails vérifiés', value: stats.visitors_verified },
    { label: 'Créations', value: stats.designs_total },
    { label: 'Rendus JPEG', value: stats.designs_rendered },
    { label: 'E-mails en attente', value: stats.emails_pending },
    { label: 'E-mails en échec', value: stats.emails_failed, alerte: stats.emails_failed > 0 },
  ]

  const soumises = timeline.filter((row) => row.name === 'design_submitted')
  const sommet = Math.max(1, ...soumises.map((row) => row.count))

  return (
    <Stack gap="xl">
      <Title order={1} fz={28}>Tableau de bord</Title>

      <SimpleGrid cols={{ base: 2, sm: 3, lg: 6 }} spacing="md">
        {cartes.map((carte) => (
          <Card key={carte.label} bd={carte.alerte ? '1px solid var(--mantine-color-red-4)' : undefined}>
            <Text fz={30} fw={700} lh={1.1} c={carte.alerte ? 'red.7' : undefined}>
              {carte.value}
            </Text>
            <Text fz="xs" c="dimmed" mt={6}>{carte.label}</Text>
          </Card>
        ))}
      </SimpleGrid>

      <div>
        <Title order={2} fz="lg" mb="sm">Créations par heure (24 h)</Title>
        <Paper withBorder radius="md" p="md">
          {soumises.length === 0 ? (
            <Text c="dimmed" fz="sm">Aucune donnée sur la période.</Text>
          ) : (
            <Group align="flex-end" gap={6} h={180} wrap="nowrap">
              {/* maw : avec une seule tranche horaire, une barre en flex:1
                  s'etalerait sur toute la largeur et ne ressemblerait plus a
                  un graphe. */}
              {soumises.map((row) => (
                <Tooltip key={row.bucket} label={`${row.count} création(s)`} withArrow>
                  <Stack gap={6} align="center" justify="flex-end" h="100%" maw={56} style={{ flex: 1 }}>
                    <div
                      style={{
                        width: '100%',
                        minHeight: 2,
                        height: `${(row.count / sommet) * 100}%`,
                        borderRadius: '4px 4px 0 0',
                        background: 'var(--mantine-color-aixam-6)',
                      }}
                    />
                    <Text fz={10} c="dimmed">{new Date(row.bucket).getHours()}h</Text>
                  </Stack>
                </Tooltip>
              ))}
            </Group>
          )}
        </Paper>
      </div>
    </Stack>
  )
}
