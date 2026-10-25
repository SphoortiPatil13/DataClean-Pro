import { Fragment, useEffect, useState } from 'react'
import CsvUploadPage from './CsvUploadPage.jsx'

function DashboardPage({ user, onHome, onLoggedOut, onSessionExpired }) {
  const [error, setError] = useState('')
  const [isLoggingOut, setIsLoggingOut] = useState(false)
  const [activeView, setActiveView] = useState('clean')
  const [history, setHistory] = useState([])
  const [historyError, setHistoryError] = useState('')
  const [isLoadingHistory, setIsLoadingHistory] = useState(false)
  const [historyRefresh, setHistoryRefresh] = useState(0)
  const [statistics, setStatistics] = useState(null)
  const [statisticsError, setStatisticsError] = useState('')
  const [isLoadingStatistics, setIsLoadingStatistics] = useState(true)
  const [statisticsRefresh, setStatisticsRefresh] = useState(0)
  const [expandedHistoryId, setExpandedHistoryId] = useState(null)
  const [downloadingHistoryId, setDownloadingHistoryId] = useState(null)
  const [historyDownloadError, setHistoryDownloadError] = useState('')

  useEffect(() => {
    let isActive = true

    async function loadStatistics() {
      setIsLoadingStatistics(true)
      setStatisticsError('')
      try {
        const response = await fetch('/api/dashboard-stats', { credentials: 'include' })
        const result = await response.json()
        if (!isActive) return
        if (response.status === 401) {
          onSessionExpired()
          return
        }
        if (!response.ok || result.status !== 'success') {
          setStatisticsError(result.message || 'Dashboard statistics could not be loaded. Please try again.')
          return
        }
        setStatistics(result.statistics)
      } catch {
        if (isActive) setStatisticsError('Could not connect to DataCleanPro. Please try again.')
      } finally {
        if (isActive) setIsLoadingStatistics(false)
      }
    }

    loadStatistics()
    return () => { isActive = false }
  }, [statisticsRefresh, onSessionExpired])

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

  function refreshAfterCleaning() {
    setHistoryRefresh((current) => current + 1)
    setStatisticsRefresh((current) => current + 1)
  }

  function refreshStatistics() {
    setStatisticsRefresh((current) => current + 1)
  }

  async function handleHistoryDownload(entry) {
    setHistoryDownloadError('')
    setDownloadingHistoryId(entry.id)
    try {
      const response = await fetch(
        `/api/cleaning-history/${entry.id}/download`,
        { credentials: 'include' },
      )
      if (response.status === 401) {
        onSessionExpired()
        return
      }
      if (!response.ok) {
        let result = {}
        try {
          result = await response.json()
        } catch {
          // Use the generic message for non-JSON error responses.
        }
        setHistoryDownloadError(
          result.message || 'The cleaned CSV could not be downloaded. Please try again.',
        )
        return
      }

      const blob = await response.blob()
      const downloadUrl = URL.createObjectURL(blob)
      const safeFilename = entry.filename.replace(/[\\/:*?"<>|]/g, '_')
      const downloadName = `${safeFilename.replace(/\.csv$/i, '') || 'cleaned'}-cleaned.csv`
      const link = document.createElement('a')
      link.href = downloadUrl
      link.download = downloadName
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(downloadUrl)
    } catch {
      setHistoryDownloadError('Could not connect to DataCleanPro. Please try again.')
    } finally {
      setDownloadingHistoryId(null)
    }
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
        <section className="dashboard-statistics" aria-label="Dashboard statistics" aria-live="polite">
          {isLoadingStatistics && (
            <p className="register-intro" role="status">Loading dashboard statistics…</p>
          )}
          {statisticsError && (
            <div>
              <p className="register-message register-message-error" role="alert">{statisticsError}</p>
              <button className="text-button" type="button" onClick={refreshStatistics}>Try again</button>
            </div>
          )}
          {!isLoadingStatistics && !statisticsError && statistics && (
            <>
              <div className="statistics-grid">
                <article className="statistic-card">
                  <p className="register-eyebrow">Total Cleaning Jobs</p>
                  <p className="statistic-value">{statistics.total_cleaning_jobs}</p>
                </article>
                <article className="statistic-card">
                  <p className="register-eyebrow">Rows Reviewed</p>
                  <p className="statistic-value">{statistics.rows_reviewed}</p>
                  <p className="statistic-note">
                    Across successful jobs; uploaded files are not uniquely identifiable.
                  </p>
                </article>
                <article className="statistic-card">
                  <p className="register-eyebrow">Total Rows Removed</p>
                  <p className="statistic-value">{statistics.total_rows_removed}</p>
                </article>
              </div>
              <section className="recent-activity-card" aria-labelledby="recent-activity-title">
                <p className="register-eyebrow">Your activity</p>
                <h2 id="recent-activity-title">Recent Cleaning Activity</h2>
                {statistics.recent_activity.length === 0 ? (
                  <p className="register-intro">
                    No cleaning activity yet. Clean a CSV to see your recent jobs here.
                  </p>
                ) : (
                  <ul className="recent-activity-list">
                    {statistics.recent_activity.map((entry, index) => (
                      <li key={`${entry.created_at}-${entry.filename}-${index}`}>
                        <div className="recent-activity-file">
                          <strong>{entry.filename}</strong>
                          <span>
                            {entry.original_row_count} rows before · {entry.final_row_count} after ·
                            {' '}{entry.rows_removed} removed
                          </span>
                        </div>
                        <time dateTime={entry.created_at}>
                          {new Date(entry.created_at).toLocaleString()}
                        </time>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </>
          )}
        </section>
        {activeView === 'clean' ? (
          <CsvUploadPage
            onSessionExpired={onSessionExpired}
            onCleaningComplete={refreshAfterCleaning}
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
                      <th scope="col">Details</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((entry) => (
                      <Fragment key={entry.id}>
                        <tr>
                          <td>{entry.filename}</td>
                          <td>{entry.operations.length ? entry.operations.join(', ') : 'No operations selected'}</td>
                          <td>{entry.original_row_count}</td>
                          <td>{entry.final_row_count}</td>
                          <td>{new Date(entry.created_at).toLocaleString()}</td>
                          <td>
                            <button
                              className="text-button history-detail-toggle"
                              type="button"
                              aria-expanded={expandedHistoryId === entry.id}
                              aria-controls={`history-details-${entry.id}`}
                              onClick={() => setExpandedHistoryId(
                                (current) => current === entry.id ? null : entry.id,
                              )}
                            >
                              {expandedHistoryId === entry.id ? 'Hide details' : 'View details'}
                            </button>
                          </td>
                        </tr>
                        {expandedHistoryId === entry.id && (
                          <tr>
                            <td className="history-details-cell" colSpan={6}>
                              <section
                                className="history-details"
                                id={`history-details-${entry.id}`}
                                aria-labelledby={`history-details-title-${entry.id}`}
                              >
                                <h3 id={`history-details-title-${entry.id}`}>{entry.filename}</h3>
                                <p className="history-details-date">
                                  {new Date(entry.created_at).toLocaleString()}
                                </p>
                                <dl className="history-details-stats">
                                  <div>
                                    <dt>Rows before cleaning</dt>
                                    <dd>{entry.original_row_count}</dd>
                                  </div>
                                  <div>
                                    <dt>Rows after cleaning</dt>
                                    <dd>{entry.final_row_count}</dd>
                                  </div>
                                  <div>
                                    <dt>Rows removed</dt>
                                    <dd>{entry.original_row_count - entry.final_row_count}</dd>
                                  </div>
                                </dl>
                                <h4>Cleaning operations</h4>
                                {entry.operations.length ? (
                                  <ul>
                                    {entry.operations.map((operation, index) => (
                                      <li key={`${entry.id}-operation-${index}`}>{operation}</li>
                                    ))}
                                  </ul>
                                ) : (
                                  <p className="register-intro">No operations were selected.</p>
                                )}
                                {entry.has_cleaned_file ? (
                                  <button
                                    className="button button-secondary history-download-button"
                                    type="button"
                                    disabled={downloadingHistoryId === entry.id}
                                    onClick={() => handleHistoryDownload(entry)}
                                  >
                                    {downloadingHistoryId === entry.id
                                      ? 'Preparing download…'
                                      : 'Download Cleaned CSV'}
                                  </button>
                                ) : (
                                  <p className="example-note">
                                    A cleaned file is not available for this older history record.
                                  </p>
                                )}
                                {historyDownloadError && downloadingHistoryId === null && (
                                  <p className="register-message register-message-error" role="alert">
                                    {historyDownloadError}
                                  </p>
                                )}
                              </section>
                            </td>
                          </tr>
                        )}
                      </Fragment>
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
