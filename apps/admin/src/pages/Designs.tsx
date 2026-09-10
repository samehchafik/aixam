import { useEffect, useState } from 'react'
import {
  Anchor, Badge, Button, Card, Group, Modal, Pagination, Select, SimpleGrid, Stack, Tabs, Text,
  TextInput, Title, UnstyledButton,
} from '@mantine/core'
import { api } from '../lib/api'

type Verdict = 'pending' | 'approved' | 'rejected'

type Row = {
  id: string
  status: string
  created_at: string
  render_url: string | null
  visitor_name: string | null
  visitor_email: string | null
  moderation: Verdict
  moderated_at: string | null
}

type Compteurs = { pending: number; approved: number; rejected: number }

const TRIS = [
  { value: 'date_desc', label: 'Plus recentes' },
  { value: 'date_asc', label: 'Plus anciennes' },
  { value: 'name_asc', label: 'Nom (A-Z)' },
  { value: 'name_desc', label: 'Nom (Z-A)' },
]

// Preselectionne sur « validees » : c'est ce qu'on vient verifier neuf fois
// sur dix, le rejet etant l'exception qu'on relit rarement.
const VERDICTS = [
  { value: 'approved', label: 'Validees' },
  { value: 'rejected', label: 'Rejetees' },
]

// Une planche fait six fois plus large que haute : a quatre colonnes elle
// devient une lamelle de 47 px, et l'animateur ne peut plus juger ce qu'il
// valide. Moins de colonnes, donc, et moins de vignettes par page.
const PAR_PAGE = 12
const date = (iso: string) => new Date(iso).toLocaleString('fr-FR')

export function Designs() {
  const [rows, setRows] = useState<Row[]>([])
  const [total, setTotal] = useState(0)
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState('date_desc')
  const [onglet, setOnglet] = useState<'attente' | 'traitees'>('attente')
  const [verdict, setVerdict] = useState('approved')
  const [page, setPage] = useState(1)
  const [compteurs, setCompteurs] = useState<Compteurs>({ pending: 0, approved: 0, rejected: 0 })
  const [rafraichir, setRafraichir] = useState(0)
  const [agrandie, setAgrandie] = useState<number | null>(null)

  const moderation = onglet === 'attente' ? 'pending' : verdict

  useEffect(() => {
    api<Compteurs>('/api/admin/designs/counts').then(setCompteurs)
  }, [rafraichir])

  // Changer de filtre ramene en page 1 : rester en page 3 d'un resultat qui
  // n'en compte plus qu'une afficherait une grille vide sans raison.
  useEffect(() => {
    setPage(1)
  }, [search, sort, moderation])

  useEffect(() => {
    const id = setTimeout(() => {
      const q = new URLSearchParams({
        limit: String(PAR_PAGE),
        offset: String((page - 1) * PAR_PAGE),
        search,
        sort,
        moderation,
      })
      api<{ total: number; items: Row[] }>(`/api/admin/designs?${q}`).then((res) => {
        setRows(res.items)
        setTotal(res.total)
        // La liste vient de changer sous la loupe : l'index pointerait une
        // autre creation, ou plus rien du tout.
        setAgrandie(null)
      })
    }, 250)
    return () => clearTimeout(id)
  }, [search, sort, moderation, page, rafraichir])

  /** Verdict de l'animateur. La creation quitte alors l'onglet ou elle etait. */
  const decider = async (id: string, decision: Verdict) => {
    await api(`/api/admin/designs/${id}/moderation`, {
      method: 'POST',
      body: JSON.stringify({ decision }),
    })
    setRafraichir((n) => n + 1)
  }

  // On ne navigue qu'entre les creations reellement rendues : une vignette en
  // echec n'a pas d'image a agrandir.
  const rendues = rows.filter((row) => row.render_url)
  const deplacer = (pas: number) =>
    setAgrandie((i) => Math.min(rendues.length - 1, Math.max(0, (i ?? 0) + pas)))
  const ouverte = agrandie === null ? null : rendues[agrandie]
  const pages = Math.max(1, Math.ceil(total / PAR_PAGE))

  return (
    <Stack gap="md">
      <Title order={1} fz={28}>
        Creations <Text span c="dimmed" fz={28} fw={400}>({total})</Text>
      </Title>

      <Tabs value={onglet} onChange={(v) => setOnglet((v as typeof onglet) ?? 'attente')}>
        <Tabs.List>
          <Tabs.Tab
            value="attente"
            rightSection={<Badge size="sm" circle variant={compteurs.pending ? 'filled' : 'light'}>{compteurs.pending}</Badge>}
          >
            A moderer
          </Tabs.Tab>
          <Tabs.Tab
            value="traitees"
            rightSection={<Badge size="sm" circle variant="light">{compteurs.approved + compteurs.rejected}</Badge>}
          >
            Traitees
          </Tabs.Tab>
        </Tabs.List>
      </Tabs>

      <Group>
        <TextInput
          placeholder="Filtrer par nom, prenom ou email"
          value={search}
          onChange={(e) => setSearch(e.currentTarget.value)}
          w={280}
          aria-label="Filtrer les creations"
        />
        <Select data={TRIS} value={sort} onChange={(v) => setSort(v ?? 'date_desc')} w={180} aria-label="Trier" />
        {onglet === 'traitees' && (
          <Select
            data={VERDICTS}
            value={verdict}
            onChange={(v) => setVerdict(v ?? 'approved')}
            w={160}
            aria-label="Filtrer par verdict"
          />
        )}
      </Group>

      {rows.length === 0 && (
        <Text c="dimmed">
          {onglet === 'attente' && !search
            ? 'Rien a moderer : tout a ete traite.'
            : 'Aucune creation ne correspond.'}
        </Text>
      )}

      <SimpleGrid cols={{ base: 1, md: 2, xl: 3 }} spacing="md">
        {rows.map((row) => (
          <Card key={row.id} padding={0}>
            {row.render_url ? (
              <UnstyledButton
                onClick={() => setAgrandie(rendues.findIndex((r) => r.id === row.id))}
                title="Agrandir"
              >
                <img src={row.render_url} alt="" loading="lazy" className="vignette-planche" />
              </UnstyledButton>
            ) : (
              <Text c="dimmed" fz="sm" ta="center" py="lg">{row.status}</Text>
            )}

            <Stack gap={2} px="md" pt="sm">
              {/* Sans nom : le visiteur a ete supprime (RGPD) ou la creation a
                  ete faite en mode demo, sans inscription. */}
              <Text fw={600} fz="sm">{row.visitor_name ?? 'Anonyme'}</Text>
              {row.visitor_email && <Text c="dimmed" fz="xs" truncate>{row.visitor_email}</Text>}
              <Text c="dimmed" fz="xs">{date(row.created_at)}</Text>
            </Stack>

            <Group gap="xs" p="md" pt="sm" wrap="nowrap">
              {onglet === 'attente' ? (
                <>
                  <Button color="teal" size="xs" flex={1} onClick={() => decider(row.id, 'approved')}>
                    Valider
                  </Button>
                  <Button color="red" size="xs" flex={1} onClick={() => decider(row.id, 'rejected')}>
                    Rejeter
                  </Button>
                </>
              ) : (
                <>
                  <Badge color={row.moderation === 'approved' ? 'teal' : 'red'} variant="light">
                    {row.moderation === 'approved' ? 'Validee' : 'Rejetee'}
                  </Badge>
                  {/* Reversible : un clic de travers se rattrape sans passer
                      par la base. */}
                  <Button
                    variant="subtle"
                    size="xs"
                    ml="auto"
                    color={row.moderation === 'approved' ? 'red' : 'teal'}
                    onClick={() => decider(row.id, row.moderation === 'approved' ? 'rejected' : 'approved')}
                  >
                    {row.moderation === 'approved' ? 'Rejeter' : 'Valider'}
                  </Button>
                </>
              )}
            </Group>
          </Card>
        ))}
      </SimpleGrid>

      {pages > 1 && (
        <Group justify="space-between">
          <Text c="dimmed" fz="sm">Page {page} sur {pages}</Text>
          <Pagination total={pages} value={page} onChange={setPage} size="sm" withEdges />
        </Group>
      )}

      {/* Modal plutot qu'une surcouche maison : piege de focus, touche Echap et
          blocage du defilement viennent avec. Restent les fleches. */}
      <Modal
        opened={ouverte !== null}
        onClose={() => setAgrandie(null)}
        fullScreen
        withCloseButton
        title={ouverte?.visitor_name ?? 'Anonyme'}
        onKeyDown={(e) => {
          if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
            e.preventDefault()
            deplacer(e.key === 'ArrowLeft' ? -1 : 1)
          }
        }}
      >
        {ouverte && (
          <Stack gap="md" h="calc(100vh - 120px)">
            <div className="loupe-image">
              <img src={ouverte.render_url!} alt="" />
            </div>
            <Group justify="space-between" wrap="wrap">
              <Stack gap={2}>
                {ouverte.visitor_email && <Text fz="sm" c="dimmed">{ouverte.visitor_email}</Text>}
                <Text fz="sm" c="dimmed">{date(ouverte.created_at)}</Text>
                <Anchor href={ouverte.render_url!} target="_blank" rel="noreferrer" fz="sm">
                  Ouvrir le JPEG
                </Anchor>
              </Stack>
              <Group>
                <Button variant="default" disabled={agrandie === 0} onClick={() => deplacer(-1)}>
                  Precedente
                </Button>
                <Text c="dimmed" fz="sm">{(agrandie ?? 0) + 1} / {rendues.length}</Text>
                <Button variant="default" disabled={agrandie === rendues.length - 1} onClick={() => deplacer(1)}>
                  Suivante
                </Button>
              </Group>
            </Group>
          </Stack>
        )}
      </Modal>
    </Stack>
  )
}
