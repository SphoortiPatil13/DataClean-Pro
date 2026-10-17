import { useState } from 'react'

const API_URL = '/api/login'
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

function LoginPage({ onBack, onRegister, onLoginSuccess, notice }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')

    const trimmedEmail = email.trim()
    if (!trimmedEmail || !password) {
      setError('Please enter your email and password.')
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

    setIsSubmitting(true)
    let response
    try {
      response = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: trimmedEmail, password }),
        credentials: 'include',
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

    if (response.status === 401) {
      setError('Invalid email or password.')
      setIsSubmitting(false)
      return
    }

    if (!response.ok || result.status !== 'success') {
      setError(result.message || 'Login could not be completed. Please try again.')
      setIsSubmitting(false)
      return
    }

    setPassword('')
    onLoginSuccess(result.user)
  }

  return (
    <main className="site-shell">
      <header className="topbar">
        <a className="brand" href="#top" onClick={(event) => { event.preventDefault(); onBack() }}>
          DataCleanPro
        </a>
        <button className="text-button" type="button" onClick={onBack}>Back to home</button>
      </header>

      <section className="register-section" id="top" aria-labelledby="login-title">
        <div className="register-card">
          <p className="register-eyebrow">Welcome back</p>
          <h1 id="login-title">Login</h1>
          <p className="register-intro">Enter your account details to sign in.</p>

          {notice && <p className="register-message register-message-error" role="alert">{notice}</p>}
          <form className="register-form" onSubmit={handleSubmit} noValidate>
              <label htmlFor="login-email">Email</label>
              <input
                id="login-email"
                name="email"
                type="email"
                autoComplete="email"
                maxLength="150"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />

              <label htmlFor="login-password">Password</label>
              <input
                id="login-password"
                name="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />

              {error && <p className="register-message register-message-error" role="alert">{error}</p>}

              <button className="button button-primary register-submit" type="submit" disabled={isSubmitting}>
                {isSubmitting ? 'Logging in…' : 'Login'}
              </button>
          </form>
          <p className="auth-switch">Need an account? <button className="text-button" type="button" onClick={onRegister}>Register</button></p>
        </div>
      </section>

      <footer className="page-footer">
        <span>DataCleanPro</span>
      </footer>
    </main>
  )
}

export default LoginPage
