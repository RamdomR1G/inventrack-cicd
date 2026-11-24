import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { useAuth } from '../auth'
import Modal, { Confirm, Field } from '../components/Modal'
import { useToast } from '../components/Toast'

const EMPTY = { name: '', email: '', password: '', role: 'user', is_active: true }

function validate(f, isNew) {
  const e = {}
  if (f.name.trim().length < 2) e.name = 'El nombre debe tener al menos 2 caracteres'
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(f.email.trim())) e.email = 'Correo electrónico inválido'
  if ((isNew || f.password) && f.password.length < 8) e.password = 'La contraseña debe tener al menos 8 caracteres'
  return e
}

function UserForm({ initial, onCancel, onSaved }) {
  const notify = useToast()
  const { user: me } = useAuth()
  const [f, setF] = useState(initial ? { ...initial, password: '' } : EMPTY)
  const [errors, setErrors] = useState({})
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const self = initial && initial.id === me.id

  async function submit(e) {
    e.preventDefault()
    const v = validate(f, !initial)
    setErrors(v)
    if (Object.keys(v).length) return
    setBusy(true)
    const body = { name: f.name.trim(), email: f.email.trim(), role: f.role, is_active: f.is_active }
    if (f.password) body.password = f.password
    try {
      const saved = initial
        ? await api(`/users/${initial.id}`, { method: 'PUT', body })
        : await api('/users', { method: 'POST', body })
      notify(initial ? 'Usuario actualizado' : 'Usuario creado')
      onSaved(saved)
    } catch (err) {
      const fe = Object.fromEntries(err.errors.map((x) => [x.field, x.message]))
      if (err.status === 409) fe.email = err.message
      setErrors(fe)
      if (!Object.keys(fe).length) notify(err.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} noValidate data-testid="user-form">
      <Field label="Nombre completo" name="name" error={errors.name}>
        <input value={f.name} onChange={set('name')} data-testid="user-name" />
      </Field>
      <Field label="Correo electrónico" name="email" error={errors.email}>
        <input type="email" value={f.email} onChange={set('email')} data-testid="user-email" />
      </Field>
      <Field label={initial ? 'Nueva contraseña (opcional)' : 'Contraseña'} name="password" error={errors.password}>
        <input type="password" value={f.password} onChange={set('password')} autoComplete="new-password" data-testid="user-password" />
      </Field>
      <div className="grid-2">
        <Field label="Rol" name="role">
          <select value={f.role} onChange={set('role')} disabled={self} data-testid="user-role">
            <option value="user">Usuario</option>
            <option value="admin">Administrador</option>
          </select>
        </Field>
        <label className="check">
          <input type="checkbox" checked={f.is_active} onChange={set('is_active')} disabled={self} data-testid="user-active" />
          Cuenta activa
        </label>
      </div>
      <div className="modal-actions">
        <button type="button" className="btn btn-ghost" onClick={onCancel}>Cancelar</button>
        <button className="btn btn-primary" disabled={busy} data-testid="user-save">{busy ? 'Guardando…' : 'Guardar'}</button>
      </div>
    </form>
  )
}

export default function Users() {
  const notify = useToast()
  const { user: me } = useAuth()
  const [data, setData] = useState({ total: 0, items: [] })
  const [q, setQ] = useState('')
  const [editing, setEditing] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      setData(await api(`/users?q=${encodeURIComponent(q)}&limit=200`))
    } catch (err) {
      notify(err.message, 'error')
    }
  }, [q, notify])

  useEffect(() => {
    const t = setTimeout(load, 250)
    return () => clearTimeout(t)
  }, [load])

  async function remove() {
    setBusy(true)
    try {
      await api(`/users/${deleting.id}`, { method: 'DELETE' })
      notify('Usuario eliminado')
      setDeleting(null)
      load()
    } catch (err) {
      notify(err.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>Usuarios</h1>
          <p className="muted">Cuentas con acceso al sistema.</p>
        </div>
        <button className="btn btn-primary" onClick={() => setEditing('new')} data-testid="user-new">+ Nuevo usuario</button>
      </div>
      <div className="toolbar">
        <input className="search" type="search" placeholder="Buscar por nombre o correo" value={q}
          onChange={(e) => setQ(e.target.value)} data-testid="user-search" aria-label="Buscar usuarios" />
      </div>
      <div className="card">
        <table className="table" data-testid="users-table">
          <thead><tr><th>Nombre</th><th>Correo</th><th>Rol</th><th>Estado</th><th /></tr></thead>
          <tbody>
            {data.items.map((u) => (
              <tr key={u.id} data-testid="user-row">
                <td><strong>{u.name}</strong>{u.id === me.id && <small className="desc">(tú)</small>}</td>
                <td>{u.email}</td>
                <td><span className={`chip ${u.role === 'admin' ? 'chip-accent' : ''}`}>{u.role === 'admin' ? 'Administrador' : 'Usuario'}</span></td>
                <td><span className={u.is_active ? 'dot-ok' : 'dot-off'}>{u.is_active ? 'Activo' : 'Inactivo'}</span></td>
                <td className="actions">
                  <button className="btn btn-sm" onClick={() => setEditing(u)} data-testid="user-edit">Editar</button>
                  {u.id !== me.id && (
                    <button className="btn btn-sm btn-danger-ghost" onClick={() => setDeleting(u)} data-testid="user-delete">Eliminar</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data.items.length === 0 && <p className="empty">No hay usuarios que coincidan.</p>}
      </div>
      {editing && (
        <Modal title={editing === 'new' ? 'Nuevo usuario' : 'Editar usuario'} onClose={() => setEditing(null)}>
          <UserForm initial={editing === 'new' ? null : editing} onCancel={() => setEditing(null)}
            onSaved={() => { setEditing(null); load() }} />
        </Modal>
      )}
      {deleting && (
        <Confirm title="Eliminar usuario" busy={busy} onCancel={() => setDeleting(null)} onConfirm={remove}
          message={<>¿Eliminar a <strong>{deleting.name}</strong> ({deleting.email})?</>} />
      )}
    </section>
  )
}
