import { useCallback, useEffect, useState } from 'react'
import { api, money } from '../api'
import Modal, { Confirm, Field } from '../components/Modal'
import { useToast } from '../components/Toast'

const EMPTY = { sku: '', name: '', category: 'General', price: '', stock: '0', description: '' }

function validate(f) {
  const e = {}
  if (!/^[A-Za-z0-9\-_]{3,40}$/.test(f.sku.trim())) e.sku = 'SKU de 3 a 40 caracteres: letras, números, - o _'
  if (f.name.trim().length < 2) e.name = 'El nombre debe tener al menos 2 caracteres'
  if (f.category.trim().length < 2) e.category = 'La categoría debe tener al menos 2 caracteres'
  if (!(Number(f.price) > 0)) e.price = 'El precio debe ser mayor que 0'
  if (!/^\d+$/.test(String(f.stock))) e.stock = 'El stock debe ser un entero mayor o igual a 0'
  return e
}

export function ProductForm({ initial, onCancel, onSaved }) {
  const notify = useToast()
  const [f, setF] = useState(initial ? { ...initial, price: String(initial.price), stock: String(initial.stock) } : EMPTY)
  const [errors, setErrors] = useState({})
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })

  async function submit(e) {
    e.preventDefault()
    const v = validate(f)
    setErrors(v)
    if (Object.keys(v).length) return
    setBusy(true)
    const body = { sku: f.sku.trim(), name: f.name.trim(), category: f.category.trim(),
      price: Number(f.price).toFixed(2), stock: Number(f.stock), description: f.description.trim() }
    try {
      const saved = initial
        ? await api(`/products/${initial.id}`, { method: 'PUT', body })
        : await api('/products', { method: 'POST', body })
      notify(initial ? 'Producto actualizado' : 'Producto creado')
      onSaved(saved)
    } catch (err) {
      const fe = Object.fromEntries(err.errors.map((x) => [x.field, x.message]))
      if (err.status === 409) fe.sku = err.message
      setErrors(fe)
      if (!Object.keys(fe).length) notify(err.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} noValidate data-testid="product-form">
      <div className="grid-2">
        <Field label="SKU" name="sku" error={errors.sku}>
          <input value={f.sku} onChange={set('sku')} data-testid="product-sku" />
        </Field>
        <Field label="Categoría" name="category" error={errors.category}>
          <input value={f.category} onChange={set('category')} data-testid="product-category" />
        </Field>
      </div>
      <Field label="Nombre" name="name" error={errors.name}>
        <input value={f.name} onChange={set('name')} data-testid="product-name" />
      </Field>
      <div className="grid-2">
        <Field label="Precio (MXN)" name="price" error={errors.price}>
          <input type="number" step="0.01" min="0" value={f.price} onChange={set('price')} data-testid="product-price" />
        </Field>
        <Field label="Stock" name="stock" error={errors.stock}>
          <input type="number" step="1" min="0" value={f.stock} onChange={set('stock')} data-testid="product-stock" />
        </Field>
      </div>
      <Field label="Descripción" name="description" error={errors.description}>
        <textarea rows="3" value={f.description} onChange={set('description')} data-testid="product-description" />
      </Field>
      <div className="modal-actions">
        <button type="button" className="btn btn-ghost" onClick={onCancel}>Cancelar</button>
        <button className="btn btn-primary" disabled={busy} data-testid="product-save">
          {busy ? 'Guardando…' : 'Guardar'}
        </button>
      </div>
    </form>
  )
}

export default function Products() {
  const notify = useToast()
  const [data, setData] = useState({ total: 0, items: [] })
  const [q, setQ] = useState('')
  const [sort, setSort] = useState('id')
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(null) // null | 'new' | product
  const [deleting, setDeleting] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setData(await api(`/products?q=${encodeURIComponent(q)}&sort=${sort}&limit=200`))
    } catch (err) {
      notify(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [q, sort, notify])

  useEffect(() => {
    const t = setTimeout(load, 250)
    return () => clearTimeout(t)
  }, [load])

  async function remove() {
    setBusy(true)
    try {
      await api(`/products/${deleting.id}`, { method: 'DELETE' })
      notify('Producto eliminado')
      setDeleting(null)
      load()
    } catch (err) {
      notify(err.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  const value = data.items.reduce((s, p) => s + Number(p.price) * p.stock, 0)
  const low = data.items.filter((p) => p.stock < 10).length

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>Productos</h1>
          <p className="muted">Catálogo e inventario disponible.</p>
        </div>
        <button className="btn btn-primary" onClick={() => setEditing('new')} data-testid="product-new">
          + Nuevo producto
        </button>
      </div>

      <div className="stats">
        <div className="stat"><small>Productos</small><strong data-testid="stat-total">{data.total}</strong></div>
        <div className="stat"><small>Valor del inventario</small><strong>{money(value)}</strong></div>
        <div className="stat"><small>Stock bajo (&lt; 10)</small><strong>{low}</strong></div>
      </div>

      <div className="toolbar">
        <input className="search" type="search" placeholder="Buscar por nombre, SKU o descripción" value={q}
          onChange={(e) => setQ(e.target.value)} data-testid="product-search" aria-label="Buscar productos" />
        <select value={sort} onChange={(e) => setSort(e.target.value)} data-testid="product-sort" aria-label="Ordenar">
          <option value="id">Más antiguos</option>
          <option value="-id">Más recientes</option>
          <option value="name">Nombre (A-Z)</option>
          <option value="price">Precio (menor a mayor)</option>
          <option value="-price">Precio (mayor a menor)</option>
          <option value="stock">Stock (menor a mayor)</option>
        </select>
      </div>

      <div className="card">
        <table className="table" data-testid="products-table">
          <thead>
            <tr><th>SKU</th><th>Nombre</th><th>Categoría</th><th className="num">Precio</th><th className="num">Stock</th><th /></tr>
          </thead>
          <tbody>
            {data.items.map((p) => (
              <tr key={p.id} data-testid="product-row">
                <td className="mono">{p.sku}</td>
                <td><strong>{p.name}</strong>{p.description && <small className="desc">{p.description}</small>}</td>
                <td><span className="chip">{p.category}</span></td>
                <td className="num">{money(p.price)}</td>
                <td className="num"><span className={p.stock < 10 ? 'badge-low' : ''}>{p.stock}</span></td>
                <td className="actions">
                  <button className="btn btn-sm" onClick={() => setEditing(p)} data-testid="product-edit">Editar</button>
                  <button className="btn btn-sm btn-danger-ghost" onClick={() => setDeleting(p)} data-testid="product-delete">Eliminar</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!loading && data.items.length === 0 && <p className="empty" data-testid="products-empty">No hay productos que coincidan.</p>}
      </div>

      {editing && (
        <Modal title={editing === 'new' ? 'Nuevo producto' : 'Editar producto'} onClose={() => setEditing(null)}>
          <ProductForm initial={editing === 'new' ? null : editing} onCancel={() => setEditing(null)}
            onSaved={() => { setEditing(null); load() }} />
        </Modal>
      )}
      {deleting && (
        <Confirm title="Eliminar producto" busy={busy} onCancel={() => setDeleting(null)} onConfirm={remove}
          message={<>¿Eliminar <strong>{deleting.name}</strong> ({deleting.sku})? Esta acción no se puede deshacer.</>} />
      )}
    </section>
  )
}
