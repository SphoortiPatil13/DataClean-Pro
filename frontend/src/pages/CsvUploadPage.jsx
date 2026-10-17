import { useState } from 'react'

const API_URL = '/api/upload'
const CLEAN_API_URL = '/api/clean'
const MAX_UPLOAD_SIZE = 5 * 1024 * 1024

function CsvUploadPage({ onSessionExpired }) {
  const [file, setFile] = useState(null)
  const [result, setResult] = useState(null)
  const [cleanResult, setCleanResult] = useState(null)
  const [cleaningOptions, setCleaningOptions] = useState({
    removeDuplicates: true,
    removeEmptyRows: true,
    trimWhitespace: true,
    handleMissing: true,
    missingStrategy: 'remove',
    missingPlaceholder: 'Not Provided',
  })
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isCleaning, setIsCleaning] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setResult(null)
    setCleanResult(null)

    if (!file) {
      setError('Choose a CSV file to upload.')
      return
    }
    if (!file.name.toLowerCase().endsWith('.csv')) {
      setError('Please choose a file with a .csv extension.')
      return
    }
    if (file.size > MAX_UPLOAD_SIZE) {
      setError('The file must be 5 MB or smaller.')
      return
    }

    const formData = new FormData()
    formData.append('file', file)
    setIsSubmitting(true)

    let response
    try {
      response = await fetch(API_URL, { method: 'POST', body: formData, credentials: 'include' })
    } catch {
      setError('Could not connect to DataCleanPro. Please check that the backend is running and try again.')
      setIsSubmitting(false)
      return
    }

    let payload
    try {
      payload = await response.json()
    } catch {
      setError('The server returned an unexpected response. Please try again.')
      setIsSubmitting(false)
      return
    }

    if (response.status === 401) {
      onSessionExpired()
      setIsSubmitting(false)
      return
    }

    if (!response.ok || payload?.status !== 'success') {
      setError(payload?.message || 'The CSV could not be uploaded. Please try again.')
      setIsSubmitting(false)
      return
    }

    setResult(payload)
    setIsSubmitting(false)
  }

  function updateCleaningOption(option, value) {
    setCleaningOptions((current) => ({ ...current, [option]: value }))
    setCleanResult(null)
  }

  async function handleClean(event) {
    event.preventDefault()
    setError('')
    setCleanResult(null)
    if (!file) {
      setError('Choose a CSV file to clean.')
      return
    }

    const formData = new FormData()
    formData.append('file', file)
    formData.append('remove_duplicates', String(cleaningOptions.removeDuplicates))
    formData.append('remove_empty_rows', String(cleaningOptions.removeEmptyRows))
    formData.append('trim_whitespace', String(cleaningOptions.trimWhitespace))
    formData.append('handle_missing', String(cleaningOptions.handleMissing))
    formData.append('missing_strategy', cleaningOptions.missingStrategy)
    formData.append('missing_placeholder', cleaningOptions.missingPlaceholder)
    setIsCleaning(true)

    let response
    try {
      response = await fetch(CLEAN_API_URL, {
        method: 'POST',
        body: formData,
        credentials: 'include',
      })
    } catch {
      setError('Could not connect to DataCleanPro. Please check that the backend is running and try again.')
      setIsCleaning(false)
      return
    }

    let payload
    try {
      payload = await response.json()
    } catch {
      setError('The server returned an unexpected response. Please try again.')
      setIsCleaning(false)
      return
    }

    if (response.status === 401) {
      onSessionExpired()
      setIsCleaning(false)
      return
    }

    if (!response.ok || payload?.status !== 'success') {
      setError(payload?.message || 'The CSV could not be cleaned. Please try again.')
      setIsCleaning(false)
      return
    }

    setCleanResult(payload)
    setIsCleaning(false)
  }

  function downloadCleanedCsv() {
    if (!cleanResult?.cleaned_csv || !file) return
    const downloadUrl = URL.createObjectURL(
      new Blob([cleanResult.cleaned_csv], { type: 'text/csv;charset=utf-8' }),
    )
    const link = document.createElement('a')
    link.href = downloadUrl
    link.download = `${file.name.replace(/\.csv$/i, '')}-cleaned.csv`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(downloadUrl)
  }

  return (
    <div className="upload-card">
      <p className="register-eyebrow">CSV preview</p>
      <h2 id="upload-title">Upload a CSV file</h2>
      <p className="register-intro">
        Choose a CSV file up to 5 MB to view its columns and first 10 rows.
        The file is processed for this request and is not saved.
      </p>

      <form className="upload-form" onSubmit={handleSubmit}>
        <label htmlFor="csv-file">CSV file</label>
        <input
          id="csv-file"
          name="file"
          type="file"
          accept=".csv,text/csv"
          onChange={(event) => {
            setFile(event.target.files?.[0] || null)
            setResult(null)
            setCleanResult(null)
            setError('')
          }}
        />
        <button className="button button-primary register-submit" type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Uploading…' : 'Upload CSV'}
        </button>
      </form>

      {error && <p className="register-message register-message-error" role="alert">{error}</p>}
      {result && (
        <section className="upload-result" aria-labelledby="preview-title" aria-live="polite">
          <h3 id="preview-title">Preview</h3>
          <p className="upload-row-count">Total rows: <strong>{result.row_count}</strong></p>
          <p className="upload-columns">
            Columns: {result.columns.length ? result.columns.join(', ') : 'None'}
          </p>
          {result.columns.length > 0 ? (
            <div className="table-scroll upload-table-scroll">
              <table className="data-table upload-table">
                <thead>
                  <tr>{result.columns.map((column, index) => <th scope="col" key={`${column}-${index}`}>{column}</th>)}</tr>
                </thead>
                <tbody>
                  {result.preview.map((row, rowIndex) => (
                    <tr key={rowIndex}>
                      {result.columns.map((column, columnIndex) => (
                        <td key={`${column}-${columnIndex}`}>{row[column] ?? ''}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="example-note">This CSV has no columns to preview.</p>
          )}
          {result.row_count === 0 && <p className="example-note">The CSV has a header but no data rows.</p>}
          <p className="example-note">Preview shows up to 10 rows.</p>
        </section>
      )}
      {result && (
        <section className="cleaning-section" aria-labelledby="cleaning-title">
          <h3 id="cleaning-title">Choose cleaning options</h3>
          <p className="upload-columns">Select the changes to apply to this CSV.</p>
          <form className="cleaning-form" onSubmit={handleClean}>
            <label className="cleaning-option">
              <input
                type="checkbox"
                checked={cleaningOptions.removeDuplicates}
                onChange={(event) => updateCleaningOption('removeDuplicates', event.target.checked)}
              />
              Remove duplicate rows
            </label>
            <label className="cleaning-option">
              <input
                type="checkbox"
                checked={cleaningOptions.removeEmptyRows}
                onChange={(event) => updateCleaningOption('removeEmptyRows', event.target.checked)}
              />
              Remove completely empty rows
            </label>
            <label className="cleaning-option">
              <input
                type="checkbox"
                checked={cleaningOptions.trimWhitespace}
                onChange={(event) => updateCleaningOption('trimWhitespace', event.target.checked)}
              />
              Trim leading and trailing whitespace
            </label>
            <label className="cleaning-option">
              <input
                type="checkbox"
                checked={cleaningOptions.handleMissing}
                onChange={(event) => updateCleaningOption('handleMissing', event.target.checked)}
              />
              Handle missing values
            </label>
            <label className="missing-strategy">
              When missing values are found
              <select
                value={cleaningOptions.missingStrategy}
                disabled={!cleaningOptions.handleMissing}
                onChange={(event) => updateCleaningOption('missingStrategy', event.target.value)}
              >
                <option value="remove">Remove rows with missing values</option>
                <option value="fill">Fill missing values</option>
              </select>
            </label>
            {cleaningOptions.handleMissing && cleaningOptions.missingStrategy === 'fill' && (
              <>
                <label className="missing-strategy">
                  Placeholder for missing values
                  <select
                    value={cleaningOptions.missingPlaceholder}
                    onChange={(event) => updateCleaningOption('missingPlaceholder', event.target.value)}
                  >
                    <option value="Not Provided">Not Provided</option>
                    <option value="N/A">N/A</option>
                    <option value="Not Available">Not Available</option>
                  </select>
                </label>
                <p className="example-note">
                  Numeric columns containing placeholders may be represented as text in the downloaded CSV.
                </p>
              </>
            )}
            <button className="button button-primary register-submit" type="submit" disabled={isCleaning}>
              {isCleaning ? 'Cleaning…' : 'Clean CSV'}
            </button>
          </form>
        </section>
      )}
      {cleanResult && (
        <section className="upload-result" aria-labelledby="clean-preview-title" aria-live="polite">
          <h3 id="clean-preview-title">Cleaned data preview</h3>
          <p className="upload-row-count">
            Rows before: <strong>{cleanResult.original_row_count}</strong>
            {' · '}
            Rows after: <strong>{cleanResult.row_count}</strong>
          </p>
          {cleanResult.unfilled_columns?.length > 0 && (
            <p className="example-note" role="status">
              Could not fill automatically because no suitable value was available for: {cleanResult.unfilled_columns.join(', ')}.
            </p>
          )}
          <button className="button button-secondary download-button" type="button" onClick={downloadCleanedCsv}>
            Download cleaned CSV
          </button>
          {cleanResult.columns.length > 0 ? (
            <div className="table-scroll upload-table-scroll">
              <table className="data-table upload-table">
                <thead>
                  <tr>{cleanResult.columns.map((column, index) => <th scope="col" key={`${column}-${index}`}>{column}</th>)}</tr>
                </thead>
                <tbody>
                  {cleanResult.preview.map((row, rowIndex) => (
                    <tr key={rowIndex}>
                      {cleanResult.columns.map((column, columnIndex) => (
                        <td key={`${column}-${columnIndex}`}>{row[column] ?? ''}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="example-note">This CSV has no columns to preview.</p>
          )}
          {cleanResult.row_count === 0 && <p className="example-note">No data rows remain after cleaning.</p>}
          <p className="example-note">Preview shows up to 10 rows.</p>
        </section>
      )}
    </div>
  )
}

export default CsvUploadPage
