import { useEffect, useState } from 'react'
import { Badge, Button, Group, Paper, PasswordInput, Stack, Table, Text, TextInput, Title } from '@mantine/core'
import { api } from '../lib/api'

type SyncCfg = {
  url: string
  token_set: boolean
  token_indice: string
  token_herite: boolean
  server_enabled: boolean
  local: { visitors: number; designs: number; events: number }
  cursors: Record<string, string | null>
  last_push_at: string | null
}

const dateFr = (iso: string | null) => (iso ? new Date(iso).toLocaleString('fr-FR') : 'jamais')

// Une liaison configuree n'est pas une liaison qui repond : on distingue ce
// qu'on sait sans reseau (adresse et jeton en place) de ce que seule la base
// maitre peut confirmer.
type Etat = 'absente' | 'inconnue' | 'verification' | 'ok' | 'injoignable'

const ETATS: Record<Etat, { couleur: string; texte: string }> = {
  absente: { couleur: 'gray', texte: 'Aucune liaison' },
  inconnue: { couleur: 'blue', texte: 'Configurée' },
  verification: { couleur: 'blue', texte: 'Vérification...' },
  ok: { couleur: 'teal', texte: 'Liaison établie' },
  injoignable: { couleur: 'red', texte: 'Injoignable' },
}

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
  const [etat, setEtat] = useState<Etat>('inconnue')
  const [detail, setDetail] = useState<string | null>(null)

  const load = () => api<SyncCfg>('/api/admin/sync').then((recu) => {
    setCfg(recu)
    return recu
  })

  const verifier = async () => {
    setEtat('verification')
    setDetail(null)
    try {
      const r = await api<{ ok: boolean; error?: string; remote?: Record<string, number | string> }>(
        '/api/admin/sync/test', { method: 'POST' },
      )
      setEtat(r.ok ? 'ok' : 'injoignable')
      setDetail(r.ok
        ? `Enregistré sous « ${r.remote!.client} » — la base maître détient `
          + `${r.remote!.visitors} visiteur(s) et ${r.remote!.designs} création(s).`
        : r.error ?? 'raison inconnue')
    } catch (erreur) {
      setEtat('injoignable')
      setDetail(String(erreur))
    }
  }

  // A l'ouverture, l'etat courant sans avoir a cliquer : configuree ou non, et
  // si oui, est-ce que la base maitre repond.
  useEffect(() => {
    load().then((recu) => {
      if (recu.server_enabled) return
      if (recu.url && recu.token_set) verifier()
      else setEtat('absente')
    })
  }, [])

  if (!cfg) return <Text c="dimmed">Chargement...</Text>

  if (cfg.server_enabled) {
    return (
      <div>
        <Title order={2} fz="lg" mb="sm">Base maître</Title>
        <Stack gap="sm" maw={560}>
          <Text c="dimmed" fz="sm">
            Ce back-office est la base maître : les remontées arrivent des back-offices des
            stands, qui poussent vers lui. Il n'y a rien à synchroniser d'ici.
          </Text>
          <Paper withBorder radius="md">
            <Table>
              <Table.Thead>
                <Table.Tr><Table.Th /><Table.Th>Reçus</Table.Th></Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                <Table.Tr><Table.Td>Visiteurs</Table.Td><Table.Td>{cfg.local.visitors}</Table.Td></Table.Tr>
                <Table.Tr><Table.Td>Créations</Table.Td><Table.Td>{cfg.local.designs}</Table.Td></Table.Tr>
                <Table.Tr><Table.Td>Événements</Table.Td><Table.Td>{cfg.local.events}</Table.Td></Table.Tr>
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
    verifier()
  }

  const push = async (tout: boolean) => {
    if (tout && !confirm(
      "Tout renvoyer réexpédie l'intégralité des données. Sans danger (rien n'est dupliqué), " +
      "mais un visiteur effacé côté serveur y réapparaîtra. Continuer ?")) return
    setBusy(true)
    setMessage(tout ? 'Renvoi complet en cours...' : 'Synchronisation en cours...')
    try {
      const r = await api<{ ok: boolean; error?: string; totaux?: Record<string, number> }>(
        `/api/admin/sync/push${tout ? '?full=true' : ''}`, { method: 'POST' },
      )
      setMessage(r.ok
        ? `Terminé : ${r.totaux!.visitors} visiteur(s), ${r.totaux!.designs} création(s), ${r.totaux!.events} événement(s) envoyés à la base maître.`
        : `Échec : ${r.error}`)
      load()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <Title order={2} fz="lg" mb="sm">Synchronisation vers la base maître</Title>
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
          <Paper withBorder radius="md" p="sm">
            <Group gap="xs" wrap="nowrap" align="baseline">
              <Badge color={ETATS[etat].couleur} variant="light">{ETATS[etat].texte}</Badge>
              <Text fz="sm" style={{ wordBreak: 'break-all' }}>
                {cfg.url || <Text span c="dimmed">adresse non renseignée</Text>}
              </Text>
            </Group>
            <Text fz="xs" c="dimmed" mt={6}>
              {cfg.token_set
                ? <>Jeton {cfg.token_indice}...{cfg.token_herite && ' — celui du relais d\u2019e-mails, aucun jeton propre à la synchronisation'}</>
                : 'Aucun jeton enregistré.'}
            </Text>
            {detail && (
              <Text fz="xs" mt={4} c={etat === 'injoignable' ? 'red' : 'dimmed'}>{detail}</Text>
            )}
          </Paper>

          <Text c="dimmed" fz="sm">
            Ce back-office produit, la base maître consolide. L'envoi ne part que dans ce sens,
            et il ne part que quand vous le demandez — rien n'est automatique. Synchroniser deux
            fois ne crée pas de doublon : chaque ligne garde son identifiant.
          </Text>

          <TextInput
            label="Adresse de la base maître"
            placeholder="https://aixam-admin.ifrit.fr"
            value={cfg.url}
            onChange={(e) => setCfg({ ...cfg, url: e.currentTarget.value })}
          />
          <PasswordInput
            label="Jeton"
            description="Le même que pour le relais d'e-mails : généré dans « Clients de relais » du back-office serveur."
            placeholder={cfg.token_set ? 'Jeton en place — laisser vide pour le garder' : 'axr_...'}
            autoComplete="off"
            value={token}
            onChange={(e) => setToken(e.currentTarget.value)}
          />

          <Group>
            <Button type="submit" color={saved ? 'teal' : undefined}>
              {saved ? 'Enregistré' : 'Enregistrer'}
            </Button>
            <Button
              type="button"
              variant="subtle"
              loading={etat === 'verification'}
              onClick={verifier}
            >
              Tester la liaison
            </Button>
          </Group>

          <Table withTableBorder>
            <Table.Thead>
              <Table.Tr>
                <Table.Th />
                <Table.Th>En local</Table.Th>
                <Table.Th>Synchronisé jusqu'au</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              <Table.Tr><Table.Td>Visiteurs</Table.Td><Table.Td>{cfg.local.visitors}</Table.Td><Table.Td c="dimmed">{dateFr(cfg.cursors.visitors)}</Table.Td></Table.Tr>
              <Table.Tr><Table.Td>Créations</Table.Td><Table.Td>{cfg.local.designs}</Table.Td><Table.Td c="dimmed">{dateFr(cfg.cursors.designs)}</Table.Td></Table.Tr>
              <Table.Tr><Table.Td>Événements</Table.Td><Table.Td>{cfg.local.events}</Table.Td><Table.Td c="dimmed">{dateFr(cfg.cursors.events)}</Table.Td></Table.Tr>
            </Table.Tbody>
          </Table>

          <Group>
            <Button type="button" loading={busy} onClick={() => push(false)}>Synchroniser maintenant</Button>
            <Button type="button" variant="subtle" disabled={busy} onClick={() => push(true)}>Tout renvoyer</Button>
          </Group>
          <Text c="dimmed" fz="sm">Dernière synchronisation : {dateFr(cfg.last_push_at)}</Text>
          {message && <Text c="dimmed" fz="sm">{message}</Text>}
        </Stack>
      </Paper>
    </div>
  )
}
