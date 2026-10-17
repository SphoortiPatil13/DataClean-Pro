import { useState } from 'react'
import CsvUploadPage from './CsvUploadPage.jsx'

function DashboardPage({ user, onHome, onLoggedOut, onSessionExpired }) {
  const [error, setError] = useState('')
  const [isLoggingOut, setIsLoggingOut] = useState(false)

  async function handleLogout() {
    setError('')
    setIsLoggingOut(true)
    try {
      const response = await fetch('/api/logout', {
        method: 'POST',
        credentials: 'include',
      })
      const result = await response.json()
      if (!response.ok || result.status !== 'success') {
        setError(result.message || 'Logout could not be completed. Please try again.')
        setIsLoggingOut(false)
        return
      }
      onLoggedOut()
    } catch {
      setError('Could not connect to DataCleanPro. Please try again.')
      setIsLoggingOut(false)
    }
  }

  return (
    <main className="site-shell">
      <header className="topbar">
        <a className="brand" href="#top" onClick={(event) => { event.preventDefault(); onHome() }}>
          DataCleanPro
        </a>
        <div className="dashboard-actions">
          <button className="text-button" type="button" onClick={onHome}>Home</button>
          <button className="text-button" type="button" onClick={handleLogout} disabled={isLoggingOut}>
            {isLoggingOut ? 'Logging out…' : 'Logout'}
          </button>
        </div>
      </header>

      <section className="dashboard-section" id="top" aria-labelledby="dashboard-title">
        <div className="dashboard-heading">
          <p className="register-eyebrow">Dashboard</p>
          <h1 id="dashboard-title">Welcome{user?.name ? `, ${user.name}` : ''}</h1>
          {user?.email && <p className="register-intro">Signed in as {user.email}</p>}
        </div>
        {error && <p className="register-message register-message-error" role="alert">{error}</p>}
        <CsvUploadPage onSessionExpired={onSessionExpired} />
      </section>

      <footer className="page-footer">
        <span>DataCleanPro</span>
      </footer>
    </main>
  )
}

export default DashboardPage
