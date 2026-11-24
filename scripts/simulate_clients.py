#!/usr/bin/env python3
"""Simulación de clientes en distintas ubicaciones y dispositivos contra InvenTrack.

Cada "usuario virtual" es un navegador Chromium (Playwright) configurado como si estuviera en otro
lugar y en otro equipo:
  - zona horaria e idioma (timezone_id / locale) y coordenadas GPS (geolocation),
  - dispositivo (laptop, celular o tablet, con su pantalla y user agent),
  - red (latencia y ancho de banda limitados con Chrome DevTools Protocol),
  - CPU (el procesador del "dispositivo" se hace más lento N veces).

Los usuarios virtuales usan el sistema real (login, búsqueda, ordenamiento, alta, edición y baja de
productos, pantalla de usuarios). El frontend reporta a OpenObserve su ubicación, zona horaria,
dispositivo, red, prueba de CPU, GPU y el tiempo PERCIBIDO de cada llamada, y el servidor reporta
su CPU y RAM. Así se compara la experiencia de cada perfil en el tablero
"Clientes y dispositivos (simulación)".

Uso:
    pip install playwright && python -m playwright install chromium
    python scripts/simulate_clients.py --url http://3.232.18.95 --email admin@inventrack.com \\
        --password '...' --minutes 5 --users 2

Por defecto corre los 5 perfiles; con --profiles cdmx,tijuana se eligen algunos.
"""
import argparse
import asyncio
import json
import os
import random
import statistics
import string
import time
from dataclasses import dataclass, field
from pathlib import Path

from playwright.async_api import Browser, Page, async_playwright, expect

MBPS = 1_000_000 / 8  # bytes por segundo en 1 Mbps


@dataclass
class Profile:
    slug: str
    name: str
    timezone: str
    locale: str
    lat: float
    lon: float
    device: str | None        # nombre de playwright.devices; None = laptop
    latency_ms: int           # latencia extra de la red (ida y vuelta)
    down_mbps: float          # 0 = sin límite
    up_mbps: float
    cpu_slowdown: int         # 1 = CPU normal; 4 = 4 veces más lenta
    network_label: str


PROFILES = {
    "cdmx": Profile("cdmx", "CDMX · laptop · fibra", "America/Mexico_City", "es-MX", 19.4326, -99.1332,
                    None, 10, 0, 0, 1, "fibra"),
    "monterrey": Profile("monterrey", "Monterrey · celular · 4G", "America/Monterrey", "es-MX", 25.6866, -100.3161,
                         "Pixel 7", 70, 9, 3, 4, "4G"),
    "tijuana": Profile("tijuana", "Tijuana · celular · 3G", "America/Tijuana", "es-MX", 32.5149, -117.0382,
                       "iPhone 13", 400, 0.4, 0.4, 6, "3G lento"),
    "merida": Profile("merida", "Mérida · tablet · WiFi lento", "America/Merida", "es-MX", 20.9674, -89.5926,
                      "iPad (gen 7)", 150, 2, 1, 2, "WiFi lento"),
    "madrid": Profile("madrid", "Madrid · laptop · fibra (otro continente)", "Europe/Madrid", "es-ES", 40.4168, -3.7038,
                      None, 140, 50, 20, 1, "fibra transatlántica"),
}


@dataclass
class Stats:
    profile: Profile
    actions: dict = field(default_factory=dict)   # acción -> [ms]
    iterations: int = 0
    errors: list = field(default_factory=list)
    created: list = field(default_factory=list)

    def add(self, action, ms):
        self.actions.setdefault(action, []).append(ms)


def p95(values):
    values = sorted(values)
    return values[min(len(values) - 1, int(round(0.95 * (len(values) - 1))))] if values else 0


async def timed(stats: Stats, action: str, coro):
    start = time.perf_counter()
    result = await coro
    stats.add(action, (time.perf_counter() - start) * 1000)
    return result


async def throttle(page: Page, prof: Profile):
    """Limita red y CPU con Chrome DevTools Protocol (solo Chromium)."""
    cdp = await page.context.new_cdp_session(page)
    await cdp.send("Network.enable")
    await cdp.send("Network.emulateNetworkConditions", {
        "offline": False, "latency": prof.latency_ms,
        "downloadThroughput": prof.down_mbps * MBPS if prof.down_mbps else -1,
        "uploadThroughput": prof.up_mbps * MBPS if prof.up_mbps else -1,
    })
    if prof.cpu_slowdown > 1:
        await cdp.send("Emulation.setCPUThrottlingRate", {"rate": prof.cpu_slowdown})


async def login(page: Page, base: str, email: str, password: str, prof: Profile, stats: Stats):
    await timed(stats, "cargar login", page.goto(f"{base}/login?ubicacion={prof.slug}", wait_until="load"))
    await page.get_by_test_id("login-email").fill(email)
    await page.get_by_test_id("login-password").fill(password)

    async def submit():
        await page.get_by_test_id("login-submit").click()
        await expect(page.get_by_test_id("products-table")).to_be_visible(timeout=60_000)
    await timed(stats, "iniciar sesión", submit())


async def iteration(page: Page, base: str, prof: Profile, stats: Stats, think: float):
    async def pause():
        await page.wait_for_timeout(int(random.uniform(0.5, 1.5) * think * 1000))

    # 1. Recargar el catálogo (mide la carga completa de la página)
    async def reload():
        await page.goto(f"{base}/productos", wait_until="load")
        await expect(page.get_by_test_id("product-row").first).to_be_visible(timeout=60_000)
    await timed(stats, "cargar productos", reload())
    await pause()

    # 2. Buscar y ordenar
    async def search():
        async with page.expect_response(lambda r: "/api/products?" in r.url and "q=" in r.url, timeout=60_000):
            await page.get_by_test_id("product-search").fill(random.choice(["Laptop", "Mouse", "Monitor", "Cable"]))
    await timed(stats, "buscar", search())
    await page.get_by_test_id("product-search").fill("")
    await pause()

    async def sort():
        async with page.expect_response(lambda r: "sort=-price" in r.url, timeout=60_000):
            await page.get_by_test_id("product-sort").select_option("-price")
    await timed(stats, "ordenar por precio", sort())
    await pause()

    # 3. Alta, edición y baja de un producto propio
    sku = f"SIM-{prof.slug[:4].upper()}-{''.join(random.choices(string.digits, k=6))}"

    async def create():
        await page.get_by_test_id("product-new").click()
        await page.get_by_test_id("product-sku").fill(sku)
        await page.get_by_test_id("product-name").fill(f"Producto simulado {prof.slug}")
        await page.get_by_test_id("product-category").fill("Simulación")
        await page.get_by_test_id("product-price").fill(f"{random.randint(50, 5000)}.00")
        await page.get_by_test_id("product-stock").fill(str(random.randint(1, 80)))
        await page.get_by_test_id("product-description").fill(f"Creado por la simulación desde {prof.name}")
        await page.get_by_test_id("product-save").click()
        await expect(page.get_by_test_id("toast").filter(has_text="Producto creado")).to_be_visible(timeout=60_000)
    await timed(stats, "crear producto", create())
    stats.created.append(sku)
    await pause()

    row = page.get_by_test_id("product-row").filter(has_text=sku)

    async def edit():
        await page.get_by_test_id("product-search").fill(sku)
        await expect(row).to_have_count(1, timeout=60_000)
        await row.get_by_test_id("product-edit").click()
        await page.get_by_test_id("product-stock").fill(str(random.randint(1, 80)))
        await page.get_by_test_id("product-save").click()
        await expect(page.get_by_test_id("toast").filter(has_text="Producto actualizado")).to_be_visible(timeout=60_000)
    await timed(stats, "editar producto", edit())
    await pause()

    async def delete():
        await row.get_by_test_id("product-delete").click()
        await page.get_by_test_id("confirm-delete").click()
        await expect(page.get_by_test_id("toast").filter(has_text="Producto eliminado")).to_be_visible(timeout=60_000)
    await timed(stats, "eliminar producto", delete())
    stats.created.remove(sku)
    await pause()

    # 4. Pantalla de usuarios
    async def users():
        await page.get_by_test_id("nav-usuarios").click()
        await expect(page.get_by_test_id("users-table")).to_be_visible(timeout=60_000)
    await timed(stats, "ver usuarios", users())
    await page.get_by_test_id("nav-productos").click()
    await pause()


async def virtual_user(browser: Browser, pw, args, prof: Profile, stats: Stats, deadline: float, n: int):
    options = dict(pw.devices[prof.device]) if prof.device else {"viewport": {"width": 1366, "height": 768}}
    options.pop("default_browser_type", None)
    context = await browser.new_context(**options, timezone_id=prof.timezone, locale=prof.locale,
                                        geolocation={"latitude": prof.lat, "longitude": prof.lon},
                                        permissions=["geolocation"])
    page = await context.new_page()
    page.set_default_timeout(60_000)
    await throttle(page, prof)
    await asyncio.sleep(n * 2)  # arranque escalonado
    try:
        await login(page, args.url, args.email, args.password, prof, stats)
        while time.time() < deadline:
            try:
                await iteration(page, args.url, prof, stats, args.think)
                stats.iterations += 1
            except Exception as e:  # noqa: BLE001 - se registra y sigue
                stats.errors.append(f"{type(e).__name__}: {str(e).splitlines()[0][:160]}")
                await page.goto(f"{args.url}/productos")
                if "/login" in page.url:
                    await login(page, args.url, args.email, args.password, prof, stats)
        await page.wait_for_timeout(6000)  # da tiempo a que el navegador envíe el último lote de métricas
    except Exception as e:  # noqa: BLE001
        stats.errors.append(f"{type(e).__name__}: {str(e).splitlines()[0][:160]}")
    finally:
        await context.close()


async def cleanup(pw, args, prefix="SIM-"):
    """Borra por la API los productos simulados que hayan quedado por un error a medio camino."""
    req = await pw.request.new_context(base_url=args.url)
    r = await req.post("/api/auth/login", data={"email": args.email, "password": args.password})
    if not r.ok:
        return 0
    headers = {"Authorization": f"Bearer {(await r.json())['access_token']}"}
    items = (await (await req.get(f"/api/products?q={prefix}&limit=200", headers=headers)).json())["items"]
    for item in items:
        if item["sku"].startswith(prefix):
            await req.delete(f"/api/products/{item['id']}", headers=headers)
    await req.dispose()
    return len(items)


def summary(all_stats: list[Stats], minutes: float) -> tuple[list[dict], str]:
    rows = []
    for st in all_stats:
        per_action = {a: {"n": len(v), "prom_ms": round(statistics.mean(v)), "p95_ms": round(p95(v))}
                      for a, v in st.actions.items()}
        everything = [x for v in st.actions.values() for x in v]
        rows.append({"perfil": st.profile.slug, "descripcion": st.profile.name, "zona_horaria": st.profile.timezone,
                     "red": st.profile.network_label, "latencia_red_ms": st.profile.latency_ms,
                     "cpu_mas_lenta": f"{st.profile.cpu_slowdown}x", "iteraciones": st.iterations,
                     "acciones": len(everything), "prom_ms": round(statistics.mean(everything)) if everything else 0,
                     "p95_ms": round(p95(everything)), "errores": len(st.errors), "por_accion": per_action})
    md = [f"## Simulación de clientes ({minutes:g} min)\n",
          "| Perfil | Zona horaria | Red | CPU | Iteraciones | Acciones | Prom. (ms) | p95 (ms) | Errores |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['descripcion']} | {r['zona_horaria']} | {r['red']} | {r['cpu_mas_lenta']} | {r['iteraciones']} | "
                  f"{r['acciones']} | {r['prom_ms']} | {r['p95_ms']} | {r['errores']} |")
    actions = sorted({a for r in rows for a in r["por_accion"]})
    md += ["", "### Tiempo promedio por acción (ms)", "",
           "| Acción | " + " | ".join(r["perfil"] for r in rows) + " |", "|---|" + "---|" * len(rows)]
    for a in actions:
        md.append(f"| {a} | " + " | ".join(str(r["por_accion"].get(a, {}).get("prom_ms", "–")) for r in rows) + " |")
    return rows, "\n".join(md) + "\n"


async def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=os.getenv("SIM_URL", "http://localhost"))
    ap.add_argument("--email", default=os.getenv("SIM_EMAIL", "admin@inventrack.com"))
    ap.add_argument("--password", default=os.getenv("SIM_PASSWORD", ""))
    ap.add_argument("--minutes", type=float, default=float(os.getenv("SIM_MINUTES", "5")))
    ap.add_argument("--users", type=int, default=int(os.getenv("SIM_USERS", "1")), help="usuarios por perfil")
    ap.add_argument("--profiles", default=os.getenv("SIM_PROFILES", ",".join(PROFILES)))
    ap.add_argument("--think", type=float, default=1.5, help="segundos de pausa promedio entre acciones")
    ap.add_argument("--out", default="reports/simulacion")
    args = ap.parse_args()
    args.url = args.url.rstrip("/")
    if not args.password:
        raise SystemExit("Falta la contraseña: --password o SIM_PASSWORD")
    chosen = [PROFILES[p.strip()] for p in args.profiles.split(",") if p.strip()]

    deadline = time.time() + args.minutes * 60
    print(f"Simulando {len(chosen)} perfiles x {args.users} usuario(s) durante {args.minutes:g} min contra {args.url}")
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        all_stats = [Stats(p) for p in chosen]
        tasks = [virtual_user(browser, pw, args, st.profile, st, deadline, i * len(chosen) + j)
                 for i in range(args.users) for j, st in enumerate(all_stats)]
        await asyncio.gather(*tasks)
        await browser.close()
        leftovers = await cleanup(pw, args)

    rows, md = summary(all_stats, args.minutes)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "resultados.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    (out / "resumen.md").write_text(md)
    errors = [f"{st.profile.slug}: {e}" for st in all_stats for e in st.errors]
    (out / "errores.txt").write_text("\n".join(errors) or "Sin errores\n")
    print(md)
    if leftovers:
        print(f"Se limpiaron {leftovers} productos simulados que quedaron pendientes.")
    if errors:
        print(f"{len(errors)} errores (ver {out / 'errores.txt'})")


if __name__ == "__main__":
    asyncio.run(main())
