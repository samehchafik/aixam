import { useEffect, useState } from 'react'
import { NavLink, Navigate, Route, HashRouter as Router, Routes } from 'react-router-dom'
import { AppShell, Box, Burger, Group, NavLink as MantineNavLink, Stack, Text, UnstyledButton } from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { auth } from './lib/api'
import { Login } from './pages/Login'
import { Dashboard } from './pages/Dashboard'
import { Visitors } from './pages/Visitors'
import { Designs } from './pages/Designs'
import { Emails } from './pages/Emails'
import { Settings } from './pages/Settings'

// Le back-office sert deux publics. L'animateur du stand n'a que deux gestes :
// regarder les visiteurs, moderer les creations. Le tableau de bord, les
// emails et les reglages sont l'affaire de celui qui installe -- en plein
// salon ils n'offrent qu'occasion de se tromper de page.
//
// La vue complete s'ouvre par l'adresse, pas par un bouton :
//
//   https://aixam-admin.ifrit.fr/#/creations        les deux pages
//   https://aixam-admin.ifrit.fr/full#/creations    tout
//
// Un bouton se cliquerait par megarde entre deux visiteurs ; une adresse se
// met en favori une fois pour toutes. Le chemin se lit une seule fois : avec
// un routage par diese, il ne bouge plus de la session, et chaque lien garde
// donc le mode ou l'on est.
//
// Ce n'est pas une permission : qui a le mot de passe garde l'API entiere.
// C'est un ecran plus court, rien de plus.
const COMPLET = /(^|\/)full\/?$/.test(window.location.pathname)

const NAV = [
  { to: '/', label: 'Tableau de bord', end: true, complet: true },
  { to: '/visiteurs', label: 'Visiteurs' },
  { to: '/creations', label: 'Créations' },
  { to: '/emails', label: 'Emails', complet: true },
  { to: '/reglages', label: 'Réglages', complet: true },
]

const PAGES = NAV.filter((item) => COMPLET || !item.complet)

// Sans tableau de bord, la racine n'a rien a montrer : l'animateur arrive sur
// ce qu'il vient faire.
const ACCUEIL = COMPLET ? '/' : '/creations'

export default function App() {
  const [authenticated, setAuthenticated] = useState(Boolean(auth.token))
  const [ouvert, { toggle, close }] = useDisclosure()

  // Une session expire en silence : c'est l'API qui l'apprend, au premier 401.
  // Sans cette ecoute, l'ecran restait sur le tableau de bord.
  useEffect(() => auth.surChangement(() => setAuthenticated(Boolean(auth.token))), [])

  if (!authenticated) return <Login />

  return (
    <Router>
      <AppShell
        header={{ height: 56 }}
        // Le menu se replie sous 768px : l'animateur consulte parfois le
        // back-office depuis une tablette, entre deux visiteurs.
        navbar={{ width: 220, breakpoint: 'sm', collapsed: { mobile: !ouvert } }}
        padding="lg"
      >
        <AppShell.Header>
          <Group h="100%" px="md" justify="space-between">
            <Group gap="sm">
              <Burger opened={ouvert} onClick={toggle} hiddenFrom="sm" size="sm" />
              <Text fw={700} fz="sm" style={{ letterSpacing: '0.16em' }}>AIXAM</Text>
              <Text c="dimmed" fz="sm" visibleFrom="sm">Back-office EASY</Text>
            </Group>
            <UnstyledButton
              onClick={() => auth.clear()}
            >
              <Text c="aixam.6" fz="sm" fw={500}>Déconnexion</Text>
            </UnstyledButton>
          </Group>
        </AppShell.Header>

        <AppShell.Navbar p="sm">
          <Stack gap={2}>
            {PAGES.map((item) => (
              <MantineNavLink
                key={item.to}
                component={NavLink}
                to={item.to}
                end={item.end}
                label={item.label}
                onClick={close}
                style={{ borderRadius: 'var(--mantine-radius-md)' }}
              />
            ))}
          </Stack>
        </AppShell.Navbar>

        <AppShell.Main>
          <Box maw={1280}>
            <Routes>
              <Route path="/visiteurs" element={<Visitors />} />
              <Route path="/creations" element={<Designs />} />
              {COMPLET && (
                <>
                  <Route path="/" element={<Dashboard />} />
                  <Route path="/emails" element={<Emails />} />
                  <Route path="/reglages" element={<Settings />} />
                </>
              )}
              {/* Une page retiree du menu l'est aussi de l'adresse : un
                  #/reglages tape a la main, ou reste d'un favori, ramene a
                  l'accueil plutot que d'ouvrir un ecran sans retour. */}
              <Route path="*" element={<Navigate to={ACCUEIL} replace />} />
            </Routes>
          </Box>
        </AppShell.Main>
      </AppShell>
    </Router>
  )
}
