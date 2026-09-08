import { useState } from 'react'
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
    <div className="login">
      <form onSubmit={submit}>
        <p className="brand">AIXAM</p>
        <h1>Back-office EASY</h1>
        <label>
          <span>Email</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label>
          <span>Mot de passe</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={busy}>
          {busy ? 'Connexion...' : 'Se connecter'}
        </button>
      </form>
    </div>
  )
}
