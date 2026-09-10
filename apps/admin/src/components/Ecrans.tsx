import { useEffect, useState } from 'react'
import {
  Alert, Badge, Button, Code, Group, Paper, Select, Stack, Table, Text, TextInput, Title,
} from '@mantine/core'
import { api } from '../lib/api'

type Ecran = {
  peripherique: string
  modele: string
  x: number
  y: number
  largeur: number
  hauteur: number
  principal: boolean
}

type Releve = {
  releve_le: string
  systeme: string
  ecrans: Ecran[]
  indisponible: string | null
}

// Ce qu'on peut afficher aujourd'hui. Le mur des créations validées viendra
// s'ajouter ici le jour où l'écran existera.
// Le script suit le systeme de la machine relevee : un .ps1 telecharge sur un
// Mac ne servirait a rien.
const SCRIPTS: Record<string, string> = {
  Windows: 'PowerShell (.ps1)',
  Darwin: 'shell (.sh)',
  Linux: 'shell (.sh)',
}

const ROLES = [
  { value: '', label: 'Ne rien lancer' },
  { value: '/kiosk/|tactile', label: 'Écran tactile (formulaire et éditeur)' },
  { value: '/kiosk/#/display|grand-ecran', label: 'Grand écran (miroir de la composition)' },
]

/** Comment on lance le script produit, selon le systeme. */
const commande = (nom: string) =>
  nom.endsWith('.ps1') ? `powershell -ExecutionPolicy Bypass -File ${nom}` : `bash ${nom}`

/** Les moniteurs de CETTE machine, et le script qui les ouvre en kiosque. */
export function Ecrans() {
  const [releve, setReleve] = useState<Releve | null>(null)
  const [roles, setRoles] = useState<Record<string, string>>({})
  const [hote, setHote] = useState(window.location.origin)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const charger = (rescan = false) =>
    api<Releve>(`/api/admin/materiel${rescan ? '?rescan=true' : ''}`).then((r) => {
      setReleve(r)
      // Deux écrans détectés et rien de choisi : la disposition la plus
      // courante au stand, qu'on propose sans l'imposer.
      setRoles((actuels) =>
        Object.keys(actuels).length || r.ecrans.length !== 2
          ? actuels
          : {
              [r.ecrans[0].peripherique]: ROLES[1].value,
              [r.ecrans[1].peripherique]: ROLES[2].value,
            },
      )
    })

  useEffect(() => {
    charger()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (!releve) return <Text c="dimmed">Chargement...</Text>

  const choisis = releve.ecrans.filter((e) => roles[e.peripherique])

  const engendrer = async () => {
    setBusy(true)
    setMessage(null)
    try {
      const res = await api<{ nom: string; script: string }>('/api/admin/materiel/lanceur', {
        method: 'POST',
        body: JSON.stringify({
          hote,
          // Le systeme vient du releve, donc de la machine qui pilote les
          // ecrans : c'est lui qui decide de la forme du script.
          systeme: releve.systeme,
          ecrans: choisis.map((e) => {
            const [chemin, profil] = roles[e.peripherique].split('|')
            return {
              peripherique: e.peripherique,
              libelle: e.modele,
              x: e.x, y: e.y, largeur: e.largeur, hauteur: e.hauteur,
              chemin, profil,
            }
          }),
        }),
      })
      const url = URL.createObjectURL(new Blob([res.script], { type: 'text/plain' }))
      const lien = document.createElement('a')
      lien.href = url
      lien.download = res.nom
      lien.click()
      URL.revokeObjectURL(url)
      setMessage(`${res.nom} téléchargé. À placer sur cette machine, puis : ${commande(res.nom)}`)
    } catch (e) {
      setMessage(`Échec : ${(e as Error).message}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <Title order={2} fz="lg" mb="sm">Écrans</Title>
      <Stack gap="md" maw={860}>
        <Text c="dimmed" fz="sm">
          Relevés par l'API, donc par la machine qui pilote réellement les écrans. Un navigateur
          ne verrait que les moniteurs du poste qui l'affiche — celui de l'animateur, pas celui
          du stand.
        </Text>

        {releve.indisponible ? (
          <Alert color="orange" variant="light" title="Aucun relevé">
            {releve.indisponible} Ouvrez ce back-office <b>sur le PC du stand</b>, en mode local
            (<Code>bin/start.sh --local</Code>), pour que les moniteurs soient détectés.
          </Alert>
        ) : (
          <Paper withBorder radius="md">
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Moniteur</Table.Th>
                  <Table.Th>Résolution</Table.Th>
                  <Table.Th>Position</Table.Th>
                  <Table.Th>Ce qu'il affiche</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {releve.ecrans.map((e) => (
                  <Table.Tr key={e.peripherique}>
                    <Table.Td>
                      <Group gap="xs">
                        <Text fw={500} fz="sm">{e.modele}</Text>
                        {e.principal && <Badge size="sm" variant="light">principal</Badge>}
                      </Group>
                      <Code>{e.peripherique}</Code>
                    </Table.Td>
                    <Table.Td>{e.largeur} × {e.hauteur}</Table.Td>
                    <Table.Td c="dimmed">{e.x}, {e.y}</Table.Td>
                    <Table.Td>
                      <Select
                        data={ROLES}
                        value={roles[e.peripherique] ?? ''}
                        onChange={(v) => setRoles({ ...roles, [e.peripherique]: v ?? '' })}
                        w={280}
                        aria-label={`Rôle de ${e.modele}`}
                      />
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Paper>
        )}

        <TextInput
          label="Adresse de l'API vue par la borne"
          description="C'est ce que Chromium ouvrira. Sur le PC du stand lui-même, localhost convient."
          value={hote}
          onChange={(e) => setHote(e.currentTarget.value)}
          w={360}
        />

        <Group>
          <Button variant="default" onClick={() => charger(true)}>Relever à nouveau</Button>
          <Button loading={busy} disabled={choisis.length === 0} onClick={engendrer}>
            Générer le script {SCRIPTS[releve.systeme] ?? 'de lancement'}
          </Button>
        </Group>
        {choisis.length === 0 && !releve.indisponible && (
          <Text c="dimmed" fz="sm">Attribuez au moins un écran pour générer le script.</Text>
        )}
        {message && <Text c="dimmed" fz="sm">{message}</Text>}

        <Text c="dimmed" fz="xs">
          Dernier relevé : {new Date(releve.releve_le).toLocaleString('fr-FR')} · {releve.systeme}.
          À refaire après tout changement de disposition : débrancher un écran ou en intervertir
          deux change les coordonnées, et le script les place par coordonnées.
        </Text>
      </Stack>
    </div>
  )
}
