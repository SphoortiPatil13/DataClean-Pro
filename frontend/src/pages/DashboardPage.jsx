import { useEffect, useState } from 'react'
import CsvUploadPage from './CsvUploadPage.jsx'

function DashboardPage({ user, onHome, onLoggedOut, onSessionExpired }) {
  const [error, setError] = useState('')
  const [isLoggingOut, setIsLoggingOut] = useState(false)
  const [activeView, setActiveView] = useState('clean')
  const [history, setHistory] = useState([])
  const [historyError, setHistoryError] = useState('')
  const [isLoadingHistory, setIsLoadingHistory] = useState(false)
  const [historyRefresh, setHistoryRefresh] = useState(0)

  useEffect(() => {
    if (activeView !== 'history') return undefined
    let isActive = true

    async function loadHistory() {
      setIsLoadingHistory(true)
      setHistoryError('')
      try {
        const response = await fetch('/api/cleaning-history', { credentials: 'include' })
        const result = await response.json()
        if (!isActive) return
        if (response.status === 401) {
          onSessionExpired()
          return
        }
        if (!response.ok || result.status !== 'success') {
          setHistoryError(result.message || 'Cleaning history could not be loaded. Please try again.')
          return
        }
        setHistory(result.history)
      } catch {
        if (isActive) setHistoryError('Could not connect to DataCleanPro. Please try again.')
      } finally {
        if (isActive) setIsLoadingHistory(false)
      }
    }

    loadHistory()
    return () => { isActive = false }
  }, [activeView, historyRefresh, onSessionExpired])

  function refreshHistory() {
    setHistoryRefresh((current) => current + 1)
  }

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
          <button
            className="text-button"
            type="button"
            aria-pressed={activeView === 'clean'}
            onClick={() => setActiveView('clean')}
          >
            Clean CSV
          </button>
          <button
            className="text-button"
            type="button"
            aria-pressed={activeView === 'history'}
            onClick={() => setActiveView('history')}
          >
            Cleaning History
          </button>
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
        {activeView === 'clean' ? (
          <CsvUploadPage
            onSessionExpired={onSessionExpired}
            onCleaningComplete={refreshHistory}
          />
        ) : (
          <section className="history-card" aria-labelledby="history-title" aria-live="polite">
            <p className="register-eyebrow">Your activity</p>
            <h2 id="history-title">Cleaning History</h2>
            {isLoadingHistory && <p className="register-intro" role="status">Loading cleaning history…</p>}
            {historyError && (
              <div>
                <p className="register-message register-message-error" role="alert">{historyError}</p>
                <button className="text-button" type="button" onClick={refreshHistory}>Try again</button>
              </div>
            )}
            {!isLoadingHistory && !historyError && history.length === 0 && (
              <p className="register-intro">No cleaning history yet. Clean a CSV to see it here.</p>
            )}
            {!isLoadingHistory && !historyError && history.length > 0 && (
              <div className="table-scroll history-table-scroll">
                <table className="data-table history-table">
                  <thead>
                    <tr>
                      <th scope="col">File</th>
                      <th scope="col">Cleaning operations</th>
                      <th scope="col">Original rows</th>
                      <th scope="col">Cleaned rows</th>
                      <th scope="col">Date and time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((entry) => (
                      <tr key={entry.id}>
                        <td>{entry.filename}</td>
                        <td>{entry.operations.length ? entry.operations.join(', ') : 'No operations selected'}</td>
                        <td>{entry.original_row_count}</td>
                        <td>{entry.final_row_count}</td>
                        <td>{new Date(entry.created_at).toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}
      </section>

      <footer className="page-footer">
        <span>DataCleanPro</span>
      </footer>
    </main>
  )
}

export default DashboardPage
