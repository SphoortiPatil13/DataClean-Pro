function LandingPage({ onLogin, onRegister, notice }) {
  return (
    <main className="site-shell">
      <header className="topbar">
        <a className="brand" href="#top">DataCleanPro</a>
      </header>

      <section className="hero" id="top" aria-labelledby="hero-title">
        <div className="hero-copy">
          <h1 id="hero-title">DataCleanPro</h1>
          <p className="hero-subtitle">Clean your CSV data quickly and easily.</p>
          <p className="hero-description">
            DataCleanPro helps identify and tidy common CSV problems such as
            extra spaces, inconsistent text, missing values, and duplicate rows.
          </p>
          <div className="hero-actions">
            <button className="button button-primary" type="button" onClick={onLogin}>Login</button>
            <button className="button button-secondary" type="button" onClick={onRegister}>Register</button>
          </div>
          {notice && <p className="register-message register-message-error" role="alert">{notice}</p>}
        </div>
      </section>

      <section className="example-section" aria-labelledby="example-title">
        <div className="section-heading">
          <h2 id="example-title">Example CSV cleanup</h2>
          <p>Common formatting issues, shown before and after cleanup.</p>
        </div>

        <div className="compare-grid">
          <section className="compare-panel" aria-labelledby="before-title">
            <div className="compare-heading">
              <h3 id="before-title">Before</h3>
              <span>Original data</span>
            </div>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr><th scope="col">Name</th><th scope="col">Email</th><th scope="col">City</th></tr>
                </thead>
                <tbody>
                  <tr><td> MAYA PATEL </td><td> maya@mail.com </td><td> pune </td></tr>
                  <tr><td>Arjun Rao</td><td className="example-issue">(blank)</td><td>Nashik </td></tr>
                  <tr><td>Arjun Rao</td><td className="example-issue">(blank)</td><td>Nashik </td></tr>
                </tbody>
              </table>
            </div>
          </section>

          <section className="compare-panel" aria-labelledby="after-title">
            <div className="compare-heading">
              <h3 id="after-title">After</h3>
              <span>Example cleaned data</span>
            </div>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr><th scope="col">Name</th><th scope="col">Email</th><th scope="col">City</th></tr>
                </thead>
                <tbody>
                  <tr><td>Maya Patel</td><td>maya@mail.com</td><td>Pune</td></tr>
                  <tr><td>Arjun Rao</td><td>Not provided</td><td>Nashik</td></tr>
                </tbody>
              </table>
            </div>
          </section>
        </div>
        <p className="example-note">Example data only. CSV upload and preview are available from the dashboard after login.</p>
      </section>

      <footer className="page-footer">
        <span>DataCleanPro</span>
      </footer>
    </main>
  )
}

export default LandingPage