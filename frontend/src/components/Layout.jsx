import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'

export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const initials = user.name.split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase()
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true" />
          InvenTrack
        </div>
        <nav aria-label="Principal">
          <NavLink to="/productos" data-testid="nav-productos">Productos</NavLink>
          {user.role === 'admin' && <NavLink to="/usuarios" data-testid="nav-usuarios">Usuarios</NavLink>}
        </nav>
        <div className="sidebar-foot">v{import.meta.env.VITE_APP_VERSION || 'dev'}</div>
      </aside>
      <div className="main">
        <header className="topbar">
          <div className="whoami" data-testid="whoami">
            <span className="avatar">{initials}</span>
            <div>
              <strong>{user.name}</strong>
              <small>{user.role === 'admin' ? 'Administrador' : 'Usuario'}</small>
            </div>
          </div>
          <button className="btn btn-ghost" data-testid="logout" onClick={() => { logout(); navigate('/login') }}>
            Cerrar sesión
          </button>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
