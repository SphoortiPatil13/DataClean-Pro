import { useState } from 'react'

const API_URL = 'http://127.0.0.1:5000/api/register'
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

function RegisterPage({ onBack, onLogin }) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setSuccess('')

    const trimmedName = name.trim()
    const trimmedEmail = email.trim()
    if (!trimmedName || !trimmedEmail || !password || !confirmPassword) {
      setError('Please complete all fields.')
      return
    }
    if (!EMAIL_PATTERN.test(trimmedEmail)) {
      setError('Please enter a valid email address.')
      return
    }
    if (!password.trim()) {
      setError('Password cannot be blank.')
      return
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }

    setIsSubmitting(true)
    let response
    try {
      response = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: trimmedName, email: trimmedEmail, password }),
      })
    } catch {
      setError('Could not connect to DataCleanPro. Please check that the backend is running and try again.')
      setIsSubmitting(false)
      return
    }

    let result
    try {
      result = await response.json()
    } catch {
      setError('The server returned an unexpected response. Please try again.')
      setIsSubmitting(false)
      return
    }

    if (!result || typeof result !== 'object') {
      setError('The server returned an unexpected response. Please try again.')
      setIsSubmitting(false)
      return
    }

    if (!response.ok || result.status !== 'success') {
      setError(
        response.status === 409
          ? 'This email is already registered. Try another email or return to the landing page.'
          : result.message || 'Registration could not be completed. Please try again.',
      )
      setIsSubmitting(false)
      return
    }

    setSuccess(result.message || 'Your account has been created successfully.')
    setIsSubmitting(false)
  }

  return (
    <main className="site-shell">
      <header className="topbar">
        <a className="brand" href="#top" onClick={(event) => { event.preventDefault(); onBack() }}>
          DataCleanPro
        </a>
        <button className="text-button" type="button" onClick={onBack}>Back to home</button>
      </header>

      <section className="register-section" id="top" aria-labelledby="register-title">
        <div className="register-card">
          <p className="register-eyebrow">Create your account</p>
          <h1 id="register-title">Register</h1>
          <p className="register-intro">A few details to get started with DataCleanPro.</p>

          {success ? (
            <div className="register-result" role="status" aria-live="polite">
              <p className="register-message register-message-success">{success}</p>
              <button className="button button-primary" type="button" onClick={onBack}>Return to home</button>
              <p className="auth-switch">Already have an account? <button className="text-button" type="button" onClick={onLogin}>Log in</button></p>
            </div>
          ) : (
            <form className="register-form" onSubmit={handleSubmit} noValidate>
              <label htmlFor="register-name">Name</label>
              <input
                id="register-name"
                name="name"
                type="text"
                autoComplete="name"
                maxLength="100"
                value={name}
                onChange={(event) => setName(event.target.value)}
                required
              />

              <label htmlFor="register-email">Email</label>
              <input
                id="register-email"
                name="email"
                type="email"
                autoComplete="email"
                maxLength="150"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />

              <label htmlFor="register-password">Password</label>
              <input
                id="register-password"
                name="password"
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />

              <label htmlFor="register-confirm-password">Confirm password</label>
              <input
                id="register-confirm-password"
                name="confirmPassword"
                type="password"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                required
              />

              {error && <p className="register-message register-message-error" role="alert">{error}</p>}

              <button className="button button-primary register-submit" type="submit" disabled={isSubmitting}>
                {isSubmitting ? 'Creating account…' : 'Create account'}
              </button>
            </form>
          )}
          {!success && (
            <p className="auth-switch">Already have an account? <button className="text-button" type="button" onClick={onLogin}>Log in</button></p>
          )}
        </div>
      </section>

      <footer className="page-footer">
        <span>DataCleanPro</span>
      </footer>
    </main>
  )
}

export default RegisterPage
