import { useState } from 'react'
import { NavLink, Navigate, Route, HashRouter as Router, Routes } from 'react-router-dom'
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

  if (!authenticated) return <Login onSuccess={() => setAuthenticated(true)} />

  return (
    <Router>
      <div className="shell">
        <aside>
          <p className="brand">AIXAM</p>
          <nav>
            {NAV.map((item) => (
              <NavLink key={item.to} to={item.to} end={item.end}>
                {item.label}
              </NavLink>
            ))}
          </nav>
          <button
            className="link logout"
            onClick={() => {
              auth.clear()
              setAuthenticated(false)
            }}
          >
            Deconnexion
          </button>
        </aside>
        <main>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/visiteurs" element={<Visitors />} />
            <Route path="/creations" element={<Designs />} />
            <Route path="/emails" element={<Emails />} />
            <Route path="/reglages" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </Router>
  )
}
