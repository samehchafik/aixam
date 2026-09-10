import { useState } from 'react'
import { Alert, Button, Center, Paper, PasswordInput, Stack, Text, TextInput, Title } from '@mantine/core'
import { api, auth } from '../lib/api'

export function Login({ onSuccess }: { onSuccess: () => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const res = await api<{ access_token: string }>('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      })
      auth.set(res.access_token)
      onSuccess()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erreur')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Center mih="100vh" p="md">
      <Paper component="form" onSubmit={submit} withBorder p="xl" radius="lg" w={380} shadow="sm">
        <Stack gap="md">
          <div>
            <Text fw={700} fz="sm" c="dimmed" style={{ letterSpacing: '0.16em' }}>AIXAM</Text>
            <Title order={2} mt={4}>Back-office EASY</Title>
          </div>

          {/* name, id et autoComplete : sans eux les gestionnaires de mots de
              passe ne reconnaissent pas le couple et ne proposent rien. */}
          <TextInput
            id="email"
            name="email"
            label="Email"
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.currentTarget.value)}
            required
          />
          <PasswordInput
            id="password"
            name="password"
            label="Mot de passe"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.currentTarget.value)}
            required
          />

          {error && <Alert color="red" variant="light">{error}</Alert>}

          <Button type="submit" loading={busy} fullWidth mt="xs">Se connecter</Button>
        </Stack>
      </Paper>
    </Center>
  )
}
