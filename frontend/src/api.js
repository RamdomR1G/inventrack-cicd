import { clientHeaders, recordApiCall } from './client'

const TOKEN_KEY = 'inventrack_token'
const USER_KEY = 'inventrack_user'

export const session = {
  get token() { return localStorage.getItem(TOKEN_KEY) },
  get user() {
    try { return JSON.parse(localStorage.getItem(USER_KEY)) } catch { return null }
  },
  save(token, user) {
    localStorage.setItem(TOKEN_KEY, token)
    localStorage.setItem(USER_KEY, JSON.stringify(user))
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  },
}

export class ApiError extends Error {
  constructor(status, detail, errors = []) {
    super(detail)
    this.status = status
    this.errors = errors
  }
}

const FIELD_MESSAGES = [
  [/at least (\d+) character/, (m) => `Debe tener al menos ${m[1]} caracteres`],
  [/at most (\d+) character/, (m) => `Debe tener como máximo ${m[1]} caracteres`],
  [/greater than or equal to (\d+)/, (m) => `Debe ser mayor o igual a ${m[1]}`],
  [/greater than (\d+)/, (m) => `Debe ser mayor que ${m[1]}`],
  [/valid email/, () => 'Correo electrónico inválido'],
  [/should match pattern/, () => 'Solo letras, números, guiones y guion bajo'],
  [/valid (integer|number|decimal)/, () => 'Debe ser un número válido'],
  [/Field required/, () => 'Campo obligatorio'],
]

export function translate(message) {
  for (const [re, fn] of FIELD_MESSAGES) {
    const m = message.match(re)
    if (m) return fn(m)
  }
  return message
}

export async function api(path, { method = 'GET', body, auth = true } = {}) {
  const headers = { Accept: 'application/json', ...clientHeaders() }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (auth && session.token) headers.Authorization = `Bearer ${session.token}`
  let res
  const start = performance.now()
  try {
    res = await fetch(`/api${path}`, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined })
  } catch {
    recordApiCall(method, path, 0, performance.now() - start)
    throw new ApiError(0, 'No se pudo conectar con el servidor')
  }
  recordApiCall(method, path, res.status, performance.now() - start)
  if (res.status === 401 && auth) {
    session.clear()
    window.dispatchEvent(new Event('inventrack:logout'))
  }
  if (res.status === 204) return null
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const errors = (data.errors || []).map((e) => ({ field: e.field, message: translate(e.message) }))
    throw new ApiError(res.status, data.detail || `Error ${res.status}`, errors)
  }
  return data
}

export const money = (v) =>
  Number(v).toLocaleString('es-MX', { style: 'currency', currency: 'MXN' })
