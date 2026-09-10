import { useState } from 'react'
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

const NAV = [
  { to: '/', label: 'Tableau de bord', end: true },
  { to: '/visiteurs', label: 'Visiteurs' },
  { to: '/creations', label: 'Creations' },
  { to: '/emails', label: 'Emails' },
  { to: '/reglages', label: 'Reglages' },
]

export default function App() {
  const [authenticated, setAuthenticated] = useState(Boolean(auth.token))
  const [ouvert, { toggle, close }] = useDisclosure()

  if (!authenticated) return <Login onSuccess={() => setAuthenticated(true)} />

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
              onClick={() => {
                auth.clear()
                setAuthenticated(false)
              }}
            >
              <Text c="aixam.6" fz="sm" fw={500}>Deconnexion</Text>
            </UnstyledButton>
          </Group>
        </AppShell.Header>

        <AppShell.Navbar p="sm">
          <Stack gap={2}>
            {NAV.map((item) => (
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
              <Route path="/" element={<Dashboard />} />
              <Route path="/visiteurs" element={<Visitors />} />
              <Route path="/creations" element={<Designs />} />
              <Route path="/emails" element={<Emails />} />
              <Route path="/reglages" element={<Settings />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Box>
        </AppShell.Main>
      </AppShell>
    </Router>
  )
}
