// Métricas del cliente (navegador): ubicación, zona horaria, dispositivo, red, CPU y GPU.
//
// Cada navegador que usa InvenTrack reporta:
//   - client_page:   tiempos de carga de la página (TTFB, DOM listo, carga completa).
//   - client_device: características del equipo y una prueba corta de CPU (benchmark en ms).
//   - client_api:    tiempo de respuesta PERCIBIDO de cada llamada a la API (incluye la red).
// Los eventos se envían en lotes a POST /api/telemetry/client y el backend los registra en
// OpenObserve. Así se compara cómo vive el sistema un usuario en CDMX con laptop frente a otro
// con un celular en 3G, aunque el servidor (EC2) sea el mismo.

const LOCATION_KEY = 'inventrack_location'
const queue = []
let flushTimer = null

// Ubicaciones conocidas por zona horaria (si no se indica ?ubicacion= en la URL).
const TZ_LOCATIONS = {
  'America/Mexico_City': 'cdmx',
  'America/Monterrey': 'monterrey',
  'America/Merida': 'merida',
  'America/Cancun': 'cancun',
  'America/Tijuana': 'tijuana',
  'America/Hermosillo': 'hermosillo',
  'America/Bogota': 'bogota',
  'America/Lima': 'lima',
  'America/New_York': 'nueva-york',
  'America/Los_Angeles': 'los-angeles',
  'Europe/Madrid': 'madrid',
  'Asia/Tokyo': 'tokio',
}

const slug = (v) => String(v || '').toLowerCase().normalize('NFD').replace(/[^a-z0-9-]+/g, '-').replace(/^-|-$/g, '').slice(0, 40)

function timezone() {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'desconocida' } catch { return 'desconocida' }
}

/** Ubicación lógica del cliente: ?ubicacion=cdmx (se recuerda en la pestaña) o la deducida de la zona horaria. */
export function clientLocation() {
  try {
    const fromUrl = new URLSearchParams(window.location.search).get('ubicacion')
    if (fromUrl) sessionStorage.setItem(LOCATION_KEY, slug(fromUrl))
    return sessionStorage.getItem(LOCATION_KEY) || TZ_LOCATIONS[timezone()] || slug(timezone())
  } catch {
    return slug(timezone())
  }
}

export function clientDevice() {
  const ua = navigator.userAgent || ''
  if (/iPad|Tablet/i.test(ua)) return 'tablet'
  if (/Mobi|Android|iPhone/i.test(ua)) return 'movil'
  return 'escritorio'
}

/** Encabezados que acompañan cada llamada a la API (el backend los agrega a sus logs). */
export function clientHeaders() {
  return { 'X-Client-Location': clientLocation(), 'X-Client-Device': clientDevice(), 'X-Client-Timezone': timezone() }
}

function gpuRenderer() {
  try {
    const gl = document.createElement('canvas').getContext('webgl')
    if (!gl) return 'sin WebGL'
    const info = gl.getExtension('WEBGL_debug_renderer_info')
    return String(info ? gl.getParameter(info.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER)).slice(0, 120)
  } catch {
    return 'desconocida'
  }
}

/** Prueba corta de CPU: tiempo en ms de una carga fija de cálculo (más ms = CPU más lenta o saturada). */
function cpuBenchmark() {
  const start = performance.now()
  let acc = 0
  for (let i = 1; i < 2_000_000; i++) acc += Math.sqrt(i) * Math.sin(i)
  return { ms: Math.round((performance.now() - start) * 10) / 10, check: acc > 0 }
}

// Coordenadas solo si el navegador YA tiene el permiso concedido (nunca se le pide al usuario).
let coords = null
function watchCoords() {
  try {
    navigator.permissions?.query({ name: 'geolocation' }).then((p) => {
      if (p.state === 'granted') {
        navigator.geolocation.getCurrentPosition((pos) => {
          coords = { lat: Math.round(pos.coords.latitude * 1e4) / 1e4, lon: Math.round(pos.coords.longitude * 1e4) / 1e4 }
        }, () => {})
      }
    }).catch(() => {})
  } catch { /* sin API de permisos */ }
}

function context() {
  const conn = navigator.connection || {}
  const now = new Date()
  return {
    ...(coords || {}),
    location: clientLocation(),
    timezone: timezone(),
    utc_offset_min: -now.getTimezoneOffset(),
    local_time: now.toLocaleString('es-MX', { hour12: false }),
    locale: navigator.language || '',
    device: clientDevice(),
    screen: `${window.screen.width}x${window.screen.height}`,
    cpu_cores: navigator.hardwareConcurrency || 0,
    memory_gb: navigator.deviceMemory || 0,
    network: conn.effectiveType || 'desconocida',
    user_agent: (navigator.userAgent || '').slice(0, 200),
  }
}

function push(event) {
  queue.push(event)
  if (queue.length >= 20) flush()
  else if (!flushTimer) flushTimer = setTimeout(flush, 5000)
}

export function flush() {
  clearTimeout(flushTimer)
  flushTimer = null
  if (!queue.length) return
  const events = queue.splice(0, 50)
  const body = JSON.stringify({ context: context(), events })
  // keepalive permite enviar el último lote aunque se cierre la pestaña
  fetch('/api/telemetry/client', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, keepalive: true })
    .catch(() => {})
}

/** Registra el tiempo percibido de una llamada a la API (lo usa api.js). */
export function recordApiCall(method, path, status, ms) {
  if (path.startsWith('/telemetry')) return
  // Agrupa rutas con ids: /products/15 -> /products/{id}
  const route = `/api${path.split('?')[0].replace(/\/\d+(?=\/|$)/g, '/{id}')}`
  push({ kind: 'api', method, route, status, ms: Math.round(ms * 10) / 10 })
}

export function initClientMetrics() {
  clientLocation()
  watchCoords()
  const report = () => {
    const nav = performance.getEntriesByType('navigation')[0]
    if (nav) {
      push({
        kind: 'page', route: window.location.pathname,
        ttfb_ms: Math.round(nav.responseStart - nav.startTime),
        dom_ms: Math.round(nav.domContentLoadedEventEnd - nav.startTime),
        load_ms: Math.round((nav.loadEventEnd || performance.now()) - nav.startTime),
      })
    }
    const bench = cpuBenchmark()
    push({ kind: 'device', cpu_bench_ms: bench.ms, long_tasks_ms: longTasks, gpu: gpuRenderer(),
           js_heap_mb: performance.memory ? Math.round(performance.memory.usedJSHeapSize / 1048576) : 0 })
    flush()
  }
  // Tiempo total del hilo principal bloqueado por tareas largas (> 50 ms): indicador de CPU saturada.
  let longTasks = 0
  try {
    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) longTasks += Math.round(e.duration - 50)
    }).observe({ type: 'longtask', buffered: true })
  } catch { /* navegador sin soporte */ }
  // Cada minuto se repite la prueba de CPU para ver su evolución mientras se usa el sistema.
  setInterval(() => {
    const bench = cpuBenchmark()
    push({ kind: 'device', cpu_bench_ms: bench.ms, long_tasks_ms: longTasks, gpu: gpuRenderer(),
           js_heap_mb: performance.memory ? Math.round(performance.memory.usedJSHeapSize / 1048576) : 0 })
  }, 60_000)
  if (document.readyState === 'complete') setTimeout(report, 500)
  else window.addEventListener('load', () => setTimeout(report, 500))
  window.addEventListener('pagehide', flush)
}
