import { useEffect, useState } from 'react'
import DashboardPage from './pages/DashboardPage.jsx'
import LandingPage from './pages/LandingPage.jsx'
import LoginPage from './pages/LoginPage.jsx'
import RegisterPage from './pages/RegisterPage.jsx'
import './App.css'

function App() {
  const [page, setPage] = useState('checking')
  const [user, setUser] = useState(null)
  const [authNotice, setAuthNotice] = useState('')

  useEffect(() => {
    let isActive = true

    async function checkSession() {
      try {
        const response = await fetch('/api/session', { credentials: 'include' })
        const result = await response.json()
        if (!isActive) return

        if (response.ok && result.status === 'success') {
          setUser(result.user)
          setPage('dashboard')
        } else if (response.status === 401) {
          setPage('landing')
        } else {
          setAuthNotice(result.message || 'Could not check your session. Please try again.')
          setPage('landing')
        }
      } catch {
        if (!isActive) return
        setAuthNotice('Could not connect to DataCleanPro. Please check that the backend is running.')
        setPage('landing')
      }
    }

    checkSession()
    return () => { isActive = false }
  }, [])

  if (page === 'checking') {
    return <main className="site-shell"><p className="register-intro" role="status">Checking your session…</p></main>
  }

  if (page === 'login') {
    return (
      <LoginPage
        onBack={() => setPage('landing')}
        onRegister={() => setPage('register')}
        onLoginSuccess={(authenticatedUser) => {
          setUser(authenticatedUser)
          setAuthNotice('')
          setPage('dashboard')
        }}
        notice={authNotice}
      />
    )
  }

  if (page === 'register') {
    return <RegisterPage onBack={() => setPage('landing')} onLogin={() => setPage('login')} />
  }

  if (page === 'dashboard') {
    return (
      <DashboardPage
        user={user}
        onHome={() => setPage('landing')}
        onLoggedOut={() => { setUser(null); setPage('landing') }}
        onSessionExpired={() => {
          setUser(null)
          setAuthNotice('Your session has expired. Please log in again.')
          setPage('login')
        }}
      />
    )
  }

  return <LandingPage
    notice={authNotice}
    onLogin={() => setPage('login')}
    onRegister={() => setPage('register')}
  />
}

export default App
