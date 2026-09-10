import { useEffect, useState } from 'react'
import { Button, Group, Paper, PasswordInput, Stack, Table, Text, TextInput, Title } from '@mantine/core'
import { api } from '../lib/api'

type SyncCfg = {
  url: string
  token_set: boolean
  server_enabled: boolean
  local: { visitors: number; designs: number; events: number }
  cursors: Record<string, string | null>
  last_push_at: string | null
}

const dateFr = (iso: string | null) => (iso ? new Date(iso).toLocaleString('fr-FR') : 'jamais')

/**
 * Remontee vers la base maitre. Sens unique : ce back-office pousse, il ne
 * recoit pas. Sur la base maitre elle-meme, le panneau se contente d'afficher
 * ce qu'elle detient -- il n'y a rien a y synchroniser.
 */
export function SyncPanel() {
  const [cfg, setCfg] = useState<SyncCfg | null>(null)
  const [token, setToken] = useState('')
  const [saved, setSaved] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const load = () => api<SyncCfg>('/api/admin/sync').then(setCfg)
  useEffect(() => {
    load()
  }, [])

  if (!cfg) return <Text c="dimmed">Chargement...</Text>

  if (cfg.server_enabled) {
    return (
      <div>
        <Title order={2} fz="lg" mb="sm">Base maitre</Title>
        <Stack gap="sm" maw={560}>
          <Text c="dimmed" fz="sm">
            Ce back-office est la base maitre : les remontees arrivent des back-offices des
            stands, qui poussent vers lui. Il n'y a rien a synchroniser d'ici.
          </Text>
          <Paper withBorder radius="md">
            <Table>
              <Table.Thead>
                <Table.Tr><Table.Th /><Table.Th>Recus</Table.Th></Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                <Table.Tr><Table.Td>Visiteurs</Table.Td><Table.Td>{cfg.local.visitors}</Table.Td></Table.Tr>
                <Table.Tr><Table.Td>Creations</Table.Td><Table.Td>{cfg.local.designs}</Table.Td></Table.Tr>
                <Table.Tr><Table.Td>Evenements</Table.Td><Table.Td>{cfg.local.events}</Table.Td></Table.Tr>
              </Table.Tbody>
            </Table>
          </Paper>
        </Stack>
      </div>
    )
  }

  const save = async () => {
    setCfg(await api<SyncCfg>('/api/admin/sync', {
      method: 'PUT',
      body: JSON.stringify({ url: cfg.url, ...(token ? { token } : {}) }),
    }))
    setToken('')
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  const test = async () => {
    setMessage('Test en cours...')
    const r = await api<{ ok: boolean; error?: string; remote?: Record<string, number | string> }>(
      '/api/admin/sync/test', { method: 'POST' },
    )
    setMessage(r.ok
      ? `Liaison etablie — enregistre sous « ${r.remote!.client} ». Le serveur detient ${r.remote!.visitors} visiteur(s) et ${r.remote!.designs} creation(s).`
      : `Echec : ${r.error}`)
  }

  const push = async (tout: boolean) => {
    if (tout && !confirm(
      "Tout renvoyer reexpedie l'integralite des donnees. Sans danger (rien n'est duplique), " +
      "mais un visiteur efface cote serveur y reapparaitra. Continuer ?")) return
    setBusy(true)
    setMessage(tout ? 'Renvoi complet en cours...' : 'Synchronisation en cours...')
    try {
      const r = await api<{ ok: boolean; error?: string; totaux?: Record<string, number> }>(
        `/api/admin/sync/push${tout ? '?full=true' : ''}`, { method: 'POST' },
      )
      setMessage(r.ok
        ? `Termine : ${r.totaux!.visitors} visiteur(s), ${r.totaux!.designs} creation(s), ${r.totaux!.events} evenement(s) envoyes a la base maitre.`
        : `Echec : ${r.error}`)
      load()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <Title order={2} fz="lg" mb="sm">Synchronisation vers la base maitre</Title>
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
        <Stack gap="md">
          <Text c="dimmed" fz="sm">
            Ce back-office produit, la base maitre consolide. L'envoi ne part que dans ce sens,
            et il ne part que quand vous le demandez — rien n'est automatique. Synchroniser deux
            fois ne cree pas de doublon : chaque ligne garde son identifiant.
          </Text>

          <TextInput
            label="Adresse de la base maitre"
            placeholder="https://aixam-admin.ifrit.fr"
            value={cfg.url}
            onChange={(e) => setCfg({ ...cfg, url: e.currentTarget.value })}
          />
          <PasswordInput
            label="Jeton"
            description="Le meme que pour le relais d'emails : genere dans « Clients de relais » du back-office serveur."
            placeholder={cfg.token_set ? 'Jeton en place — laisser vide pour le garder' : 'axr_...'}
            autoComplete="off"
            value={token}
            onChange={(e) => setToken(e.currentTarget.value)}
          />

          <Group>
            <Button type="submit" color={saved ? 'teal' : undefined}>
              {saved ? 'Enregistre' : 'Enregistrer'}
            </Button>
            <Button type="button" variant="subtle" onClick={test}>Tester la liaison</Button>
          </Group>

          <Table withTableBorder>
            <Table.Thead>
              <Table.Tr>
                <Table.Th />
                <Table.Th>En local</Table.Th>
                <Table.Th>Synchronise jusqu'au</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              <Table.Tr><Table.Td>Visiteurs</Table.Td><Table.Td>{cfg.local.visitors}</Table.Td><Table.Td c="dimmed">{dateFr(cfg.cursors.visitors)}</Table.Td></Table.Tr>
              <Table.Tr><Table.Td>Creations</Table.Td><Table.Td>{cfg.local.designs}</Table.Td><Table.Td c="dimmed">{dateFr(cfg.cursors.designs)}</Table.Td></Table.Tr>
              <Table.Tr><Table.Td>Evenements</Table.Td><Table.Td>{cfg.local.events}</Table.Td><Table.Td c="dimmed">{dateFr(cfg.cursors.events)}</Table.Td></Table.Tr>
            </Table.Tbody>
          </Table>

          <Group>
            <Button type="button" loading={busy} onClick={() => push(false)}>Synchroniser maintenant</Button>
            <Button type="button" variant="subtle" disabled={busy} onClick={() => push(true)}>Tout renvoyer</Button>
          </Group>
          <Text c="dimmed" fz="sm">Derniere synchronisation : {dateFr(cfg.last_push_at)}</Text>
          {message && <Text c="dimmed" fz="sm">{message}</Text>}
        </Stack>
      </Paper>
    </div>
  )
}
