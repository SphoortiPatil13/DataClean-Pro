import { useState } from 'react'

const API_URL = '/api/upload'
const CLEAN_API_URL = '/api/clean'
const VALIDATION_API_URL = '/api/validate-data-types'
const MAX_UPLOAD_SIZE = 5 * 1024 * 1024
const HIDDEN_ROW_NUMBER_KEY = '__data_cleanpro_original_row_number__'
const DATA_TYPES = ['text', 'integer', 'decimal', 'date']

function escapeCsvValue(value) {
  if (value === null || value === undefined) {
    return ''
  }

  const text = String(value)
  if (/[",\n\r]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`
  }
  return text
}

function rowsToCsv(columns, rows) {
  if (!Array.isArray(columns) || columns.length === 0) {
    return ''
  }

  const header = columns.map((column) => escapeCsvValue(column)).join(',')
  const values = rows.map((row) => columns.map((column) => escapeCsvValue(row?.[column])).join(','))
  return [header, ...values].join('\n')
}

function getQualitySnapshot(rows) {
  const totalRows = rows.length
  const missingValues = rows.reduce((count, row) => {
    const values = Object.values(row || {})
    return count + values.filter((value) => value === null || value === undefined || String(value).trim() === '').length
  }, 0)
  const emptyRows = rows.filter((row) => Object.values(row || {}).every((value) => value === null || value === undefined || String(value).trim() === '')).length
  const duplicateRows = rows.reduce((count, row) => {
    const index = rows.findIndex((candidate) => JSON.stringify(candidate) === JSON.stringify(row))
    return count + (index === rows.indexOf(row) ? 0 : 1)
  }, 0)

  return {
    total_rows: totalRows,
    missing_values: missingValues,
    duplicate_rows: duplicateRows,
    empty_rows: emptyRows,
  }
}

function getCurrentRows(cleanResult) {
  if (Array.isArray(cleanResult?.full_rows) && cleanResult.full_rows.length > 0) {
    return cleanResult.full_rows
  }
  if (Array.isArray(cleanResult?.full_rows)) {
    return cleanResult.full_rows
  }
  if (Array.isArray(cleanResult?.preview)) {
    return cleanResult.preview
  }
  return []
}

function CsvUploadPage({ onSessionExpired, onCleaningComplete }) {
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
  const [columnName, setColumnName] = useState('')
  const [columnFillMode, setColumnFillMode] = useState('empty')
  const [columnDefaultValue, setColumnDefaultValue] = useState('')
  const [validationTypes, setValidationTypes] = useState({})
  const [validationReport, setValidationReport] = useState(null)
  const [validationError, setValidationError] = useState('')
  const [selectedColumnForRemoval, setSelectedColumnForRemoval] = useState('')
  const [removalMode, setRemovalMode] = useState('selected')

  function updateValidationMap(columns) {
    const nextValues = {}
    columns.forEach((column) => {
      nextValues[column] = validationTypes[column] || 'text'
    })
    setValidationTypes(nextValues)
  }

  function syncResultRows(nextRows, nextColumns) {
    setCleanResult((current) => {
      const base = current || {}
      const columns = Array.isArray(nextColumns) ? nextColumns : base.columns || []
      const rows = Array.isArray(nextRows) ? nextRows : []
      const currentQuality = base.quality_report || { before: { total_rows: 0, missing_values: 0, duplicate_rows: 0, empty_rows: 0 }, after: { total_rows: 0, missing_values: 0, duplicate_rows: 0, empty_rows: 0 }, rows_removed: 0 }
      const nextQuality = {
        before: currentQuality.before || { total_rows: 0, missing_values: 0, duplicate_rows: 0, empty_rows: 0 },
        after: getQualitySnapshot(rows),
        rows_removed: Math.max((base.original_row_count || rows.length) - rows.length, 0),
      }
      return {
        ...base,
        columns,
        row_count: rows.length,
        preview: rows.slice(0, 10),
        full_rows: rows,
        cleaned_csv: rowsToCsv(columns, rows),
        quality_report: nextQuality,
      }
    })
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setResult(null)
    setCleanResult(null)
    setValidationReport(null)
    setValidationError('')

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
    setValidationReport(null)
    setValidationError('')
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
    updateValidationMap(payload.columns || [])
    setSelectedColumnForRemoval(payload.columns?.[0] || '')
    onCleaningComplete?.()
    setIsCleaning(false)
  }

  function handleAddColumn(event) {
    event.preventDefault()
    setError('')
    if (!cleanResult) {
      setError('Upload and clean a CSV before adding a column.')
      return
    }

    const trimmedName = columnName.trim()
    if (!trimmedName) {
      setError('Enter a column name before adding it.')
      return
    }

    const columns = cleanResult.columns || []
    const duplicate = columns.some((column) => column.trim().toLowerCase() === trimmedName.toLowerCase())
    if (duplicate) {
      setError('That column name already exists. Choose a different name.')
      return
    }

    const baseRows = getCurrentRows(cleanResult)
    const nextRows = baseRows.map((row) => ({ ...row, [trimmedName]: columnFillMode === 'default' ? columnDefaultValue : '' }))
    const nextColumns = [...columns, trimmedName]
    syncResultRows(nextRows, nextColumns)
    updateValidationMap(nextColumns)
    setColumnName('')
    setColumnDefaultValue('')
    setColumnFillMode('empty')
    setValidationReport(null)
    setValidationError('')
  }

  async function handleValidateColumns() {
    setValidationError('')
    if (!cleanResult?.cleaned_csv) {
      setValidationError('Clean a CSV before validating data types.')
      return
    }

    const expectedTypes = {}
    cleanResult.columns.forEach((column) => {
      expectedTypes[column] = validationTypes[column] || 'text'
    })

    try {
      const response = await fetch(VALIDATION_API_URL, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ csv: cleanResult.cleaned_csv, expected_types: expectedTypes }),
      })
      const payload = await response.json()
      if (response.status === 401) {
        onSessionExpired()
        return
      }
      if (!response.ok || payload?.status !== 'success') {
        throw new Error(payload?.message || 'Data type validation could not be completed.')
      }
      setValidationReport(payload.validation_report)
      if (!payload.validation_report || payload.validation_report.total_invalid_cells === 0) {
        setValidationError('No datatype errors were found in the selected columns.')
      }
    } catch (error) {
      setValidationError(error.message || 'Data type validation could not be completed. Please try again.')
    }
  }

  function handleKeepRows() {
    setValidationReport(null)
    setValidationError('')
  }

  function handleRemoveRows() {
    if (!validationReport || validationReport.total_invalid_cells === 0) {
      setValidationError('No datatype errors were detected, so there are no rows to remove.')
      return
    }

    const invalidEntries = validationReport.invalid_cells || []
    let rowsToRemove = []

    if (removalMode === 'selected') {
      const targetColumn = selectedColumnForRemoval || validationReport.validated_columns?.[0]
      rowsToRemove = invalidEntries.filter((entry) => entry.column === targetColumn)
    } else {
      rowsToRemove = invalidEntries
    }

    const rowNumbers = new Set(rowsToRemove.map((entry) => Number(entry.row_number)))
    const rows = getCurrentRows(cleanResult)
    const beforeCount = rows.length
    const nextRows = rows.filter((row) => {
      const rowNumber = Number(row[HIDDEN_ROW_NUMBER_KEY] ?? (rows.indexOf(row) + 2))
      return !rowNumbers.has(rowNumber)
    })

    const confirmationMessage = `${nextRows.length === beforeCount ? 'No rows will be removed' : `Remove ${beforeCount - nextRows.length} row${beforeCount - nextRows.length === 1 ? '' : 's'}?`}`
    if (!window.confirm(confirmationMessage)) {
      return
    }

    syncResultRows(nextRows, cleanResult.columns)
    setValidationReport(null)
    setValidationError('')
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
            setValidationReport(null)
            setValidationError('')
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
          {cleanResult.quality_report && (
            <section className="quality-report" aria-labelledby="quality-report-title">
              <h3 id="quality-report-title">Data Quality Report</h3>
              <p className="example-note">
                Missing values count cells; duplicate rows count repeats after the first occurrence;
                empty rows contain only missing values.
              </p>
              <div className="table-scroll quality-report-scroll">
                <table className="data-table quality-report-table">
                  <thead>
                    <tr>
                      <th scope="col">Measure</th>
                      <th scope="col">Before cleaning</th>
                      <th scope="col">After cleaning</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <th scope="row">Total rows</th>
                      <td>{cleanResult.quality_report.before.total_rows}</td>
                      <td>{cleanResult.quality_report.after.total_rows}</td>
                    </tr>
                    <tr>
                      <th scope="row">Missing values</th>
                      <td>{cleanResult.quality_report.before.missing_values}</td>
                      <td>{cleanResult.quality_report.after.missing_values}</td>
                    </tr>
                    <tr>
                      <th scope="row">Duplicate rows</th>
                      <td>{cleanResult.quality_report.before.duplicate_rows}</td>
                      <td>{cleanResult.quality_report.after.duplicate_rows}</td>
                    </tr>
                    <tr>
                      <th scope="row">Completely empty rows</th>
                      <td>{cleanResult.quality_report.before.empty_rows}</td>
                      <td>{cleanResult.quality_report.after.empty_rows}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <p className="quality-rows-removed">
                Rows removed: <strong>{cleanResult.quality_report.rows_removed}</strong>
              </p>
            </section>
          )}
          {cleanResult.unfilled_columns?.length > 0 && (
            <p className="example-note" role="status">
              Could not fill automatically because no suitable value was available for: {cleanResult.unfilled_columns.join(', ')}.
            </p>
          )}
          <div className="advanced-actions">
            <h3>Column and validation tools</h3>
            <form className="column-form" onSubmit={handleAddColumn}>
              <label>
                New column name
                <input type="text" value={columnName} onChange={(event) => setColumnName(event.target.value)} />
              </label>
              <label className="column-fill-mode">
                Fill option
                <select value={columnFillMode} onChange={(event) => setColumnFillMode(event.target.value)}>
                  <option value="empty">Create empty column</option>
                  <option value="default">Use a default value for every row</option>
                </select>
              </label>
              {columnFillMode === 'default' && (
                <label>
                  Default value
                  <input type="text" value={columnDefaultValue} onChange={(event) => setColumnDefaultValue(event.target.value)} />
                </label>
              )}
              <div className="button-row">
                <button className="button button-primary" type="submit">Add column</button>
                <button className="button button-secondary" type="button" onClick={() => { setColumnName(''); setColumnDefaultValue(''); setColumnFillMode('empty') }}>Cancel</button>
              </div>
            </form>
            <div className="validation-panel">
              <h4>Validate data types</h4>
              {cleanResult.columns.map((column) => (
                <label className="validation-field" key={column}>
                  {column}
                  <select
                    value={validationTypes[column] || 'text'}
                    onChange={(event) => setValidationTypes((current) => ({ ...current, [column]: event.target.value }))}
                  >
                    {DATA_TYPES.map((type) => <option key={type} value={type}>{type}</option>)}
                  </select>
                </label>
              ))}
              <div className="button-row">
                <button className="button button-primary" type="button" onClick={handleValidateColumns}>Validate selected columns</button>
              </div>
            </div>
            {validationReport && (
              <div className="validation-report" aria-live="polite">
                <h4>Validation result</h4>
                <p className="validation-summary">
                  <strong>{validationReport.total_invalid_cells}</strong> invalid cells across <strong>{validationReport.distinct_rows_with_errors}</strong> rows.
                </p>
                {validationReport.total_invalid_cells === 0 ? (
                  <p className="example-note">No datatype errors found. The current dataset is valid for the selected rules.</p>
                ) : (
                  <>
                    <ul className="validation-list">
                      {validationReport.invalid_cells.slice(0, 20).map((entry, index) => (
                        <li key={`${entry.row_number}-${entry.column}-${index}`}>
                          <strong>Row {entry.row_number}</strong> · {entry.column} · {entry.expected_type} · {entry.value || 'empty'} · {entry.message}
                        </li>
                      ))}
                    </ul>
                    {validationReport.invalid_cells.length > 20 && (
                      <p className="example-note">Showing the first 20 of {validationReport.total_invalid_cells} invalid cells.</p>
                    )}
                    <div className="row-removal-panel">
                      <label className="missing-strategy">
                        Correction action
                        <select value={removalMode} onChange={(event) => setRemovalMode(event.target.value)}>
                          <option value="selected">Remove rows with errors in the selected column</option>
                          <option value="all">Remove all rows with datatype errors</option>
                        </select>
                      </label>
                      {removalMode === 'selected' && (
                        <label className="missing-strategy">
                          Target column
                          <select value={selectedColumnForRemoval} onChange={(event) => setSelectedColumnForRemoval(event.target.value)}>
                            {cleanResult.columns.map((column) => (
                              <option key={column} value={column}>{column}</option>
                            ))}
                          </select>
                        </label>
                      )}
                      <div className="button-row">
                        <button className="button button-danger" type="button" onClick={handleRemoveRows}>Remove rows</button>
                        <button className="button button-secondary" type="button" onClick={handleKeepRows}>Keep rows unchanged</button>
                      </div>
                    </div>
                  </>
                )}
              </div>
            )}
            {validationError && <p className="register-message register-message-error" role="alert">{validationError}</p>}
          </div>
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
