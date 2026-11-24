import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setError('')
    if (!email.trim() || !password) {
      setError('Ingresa tu correo y tu contraseña')
      return
    }
    setBusy(true)
    try {
      await login(email.trim(), password)
      navigate('/productos')
    } catch (err) {
      setError(err.status === 422 ? 'Correo electrónico inválido' : err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-page">
      <section className="login-art" aria-hidden="true">
        <div>
          <span className="brand-mark big" />
          <h1>InvenTrack</h1>
          <p>Control de inventario con entrega continua y observabilidad.</p>
        </div>
      </section>
      <section className="login-panel">
        <form className="login-card" onSubmit={submit} noValidate data-testid="login-form">
          <h2>Iniciar sesión</h2>
          <p className="muted">Usa tu cuenta para entrar al sistema.</p>
          <label className="field">
            <span>Correo electrónico</span>
            <input type="email" name="email" autoComplete="username" value={email}
              onChange={(e) => setEmail(e.target.value)} data-testid="login-email" />
          </label>
          <label className="field">
            <span>Contraseña</span>
            <input type="password" name="password" autoComplete="current-password" value={password}
              onChange={(e) => setPassword(e.target.value)} data-testid="login-password" />
          </label>
          {error && <div className="alert" role="alert" data-testid="login-error">{error}</div>}
          <button className="btn btn-primary wide" disabled={busy} data-testid="login-submit">
            {busy ? 'Entrando…' : 'Entrar'}
          </button>
        </form>
      </section>
    </div>
  )
}
