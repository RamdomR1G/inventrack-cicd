#!/usr/bin/env python3
"""Configura OpenObserve: tableros (dashboards), destino y alertas operativas.

Uso (en la EC2 o en local):
    O2_URL=http://localhost:5080 O2_USER=admin@... O2_PASSWORD=... python3 scripts/o2_setup.py

Es idempotente: si un tablero o alerta ya existe con el mismo título/nombre, lo reemplaza.
Además guarda los JSON generados en observability/dashboards/ para importarlos a mano.
"""
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

O2_URL = os.getenv("O2_URL", "http://localhost:5080").rstrip("/")
O2_USER = os.getenv("O2_USER", "admin@inventrack.com")
O2_PASSWORD = os.getenv("O2_PASSWORD", "")
ORG = "default"
# URL con la que OpenObserve se llama a sí mismo para registrar las alertas disparadas
SELF_URL = os.getenv("O2_SELF_URL", "http://localhost:5080")
OUT = Path(__file__).resolve().parent.parent / "observability" / "dashboards"
AUTH = "Basic " + base64.b64encode(f"{O2_USER}:{O2_PASSWORD}".encode()).decode()


def call(method, path, body=None, ok=(200, 201)):
    req = urllib.request.Request(f"{O2_URL}{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "Authorization": AUTH})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode()
            return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        if e.code in ok:
            return e.code, raw
        return e.code, raw


# ------------------------------------------------------------------ paneles --- #
_pid = 0


def _base(title, kind, query_type, queries, x, y, w, h, unit=None, description="", decimals=2, extra_config=None):
    global _pid
    _pid += 1
    config = {"show_legends": True, "legends_position": "bottom", "decimals": decimals, "axis_border_show": False,
              "legend_width": {"unit": "px"}, "base_map": {"type": "osm"},
              "map_view": {"zoom": 1, "lat": 0, "lng": 0},
              "map_symbol_config": {"size": "by Value", "min": 1, "max": 100},
              "connect_nulls": True, "no_value_replacement": "", "wrap_table_cells": False,
              "table_transpose": False, "table_dynamic_columns": False, "mark_line": [], "override_config": []}
    if unit:
        config["unit"] = unit
    if unit and unit.startswith("custom:"):
        config["unit"], config["unit_custom"] = "custom", unit.split(":", 1)[1]
    config.update(extra_config or {})
    return {"id": f"Panel_ID{_pid}", "type": kind, "title": title, "description": description,
            "config": config, "queryType": query_type, "queries": queries,
            "layout": {"x": x, "y": y, "w": w, "h": h, "i": _pid},
            "htmlContent": "", "markdownContent": "", "customChartContent": ""}


def promql(title, exprs, x, y, w=24, h=9, unit=None, kind="line", description="", decimals=2, min_=None, max_=None):
    """exprs: lista de (expresión PromQL, leyenda)."""
    queries = []
    for expr, legend in exprs:
        stream = expr.split("{")[0].split("(")[-1].strip()
        cfg = {"promql_legend": legend, "layer_type": "scatter", "weight_fixed": 1, "limit": 0, "time_shift": []}
        if min_ is not None:
            cfg["min"] = min_
        if max_ is not None:
            cfg["max"] = max_
        queries.append({"query": expr, "vrlFunctionQuery": "", "customQuery": True,
                        "fields": {"stream": stream, "stream_type": "metrics", "x": [], "y": [], "z": [],
                                   "filter": {"filterType": "group", "logicalOperator": "AND", "conditions": []}},
                        "config": cfg})
    return _base(title, kind, "promql", queries, x, y, w, h, unit, description, decimals)


def sql(title, query, stream, stream_type, xs, ys, zs, x, y, w=24, h=9, kind="line", unit=None, description="",
        decimals=2, labels=None):
    """xs/ys/zs: alias de columnas del query para ejes x, y y desglose (breakdown)."""
    names = {**LABELS, **(labels or {})}

    def col(alias, color=None):
        label = names.get(alias, alias)
        return {"label": label, "alias": alias, "column": alias, "color": color, "isDerived": False}
    queries = [{"query": query, "vrlFunctionQuery": "", "customQuery": True,
                "fields": {"stream": stream, "stream_type": stream_type,
                           "x": [col(a) for a in xs], "y": [col(a, "#0f766e") for a in ys],
                           "z": [col(a) for a in zs], "breakdown": [col(a) for a in zs],
                           "filter": {"filterType": "group", "logicalOperator": "AND", "conditions": []}},
                "config": {"promql_legend": "", "layer_type": "scatter", "weight_fixed": 1, "limit": 0,
                           "min": 0, "max": 100, "time_shift": []}}]
    return _base(title, kind, "sql", queries, x, y, w, h, unit, description, decimals)


LABELS = {"x_axis_1": "Hora", "y_axis_1": "Total", "y_axis_2": "Total 2", "breakdown_1": "Serie"}


def dashboard(title, description, panels, period="30m"):
    return {"version": 5, "title": title, "description": description, "role": "", "owner": O2_USER,
            "tabs": [{"tabId": "default", "name": "Default", "panels": panels}],
            "variables": {"list": [], "showDynamicFilters": True},
            "defaultDatetimeDuration": {"type": "relative", "relativeTimePeriod": period, "startTime": 0, "endTime": 0}}


NET = 'device!~"lo|docker.*|veth.*|br-.*"'


def infra_dashboard():
    return dashboard("Infraestructura EC2", "CPU, memoria RAM, ancho de banda, temperatura, disco y carga del servidor", [
        promql("CPU (%)", [('100 * (1 - avg(system_cpu_utilization{state="idle"}))', "CPU usada")],
               0, 0, 24, 9, unit="percent", min_=0, max_=100),
        promql("Memoria RAM (%)", [('100 * sum(system_memory_utilization{state="used"})', "RAM usada")],
               24, 0, 24, 9, unit="percent", min_=0, max_=100),
        promql("Ancho de banda (Mbps)", [
            (f'sum(rate(node_network_receive_bytes_total{{{NET}}}[2m])) * 8 / 1000000', "Entrada"),
            (f'sum(rate(node_network_transmit_bytes_total{{{NET}}}[2m])) * 8 / 1000000', "Salida")],
            0, 9, 24, 9, unit="custom:Mbps", decimals=3),
        promql("Temperatura (°C)", [
            ("max by (chip, sensor) (node_hwmon_temp_celsius)", "{chip} {sensor}"),
            ("max by (zone, type) (node_thermal_zone_temp)", "zona {zone} {type}")],
            24, 9, 24, 9, unit="custom:°C",
            description="Sensores hwmon / thermal_zone leídos por node-exporter. En instancias virtualizadas de "
                        "AWS el hipervisor puede no exponer sensores; en ese caso el panel queda sin datos."),
        promql("Memoria usada (MB)", [
            ('sum(system_memory_usage{state="used"}) / 1048576', "Usada"),
            ('sum(system_memory_usage{state=~"free|cached|buffered"}) / 1048576', "Libre + caché")],
            0, 18, 16, 9, unit="custom:MB"),
        promql("Carga del sistema", [("avg(system_cpu_load_average_1m)", "1 min"),
                                     ("avg(system_cpu_load_average_5m)", "5 min")], 16, 18, 16, 9),
        promql("Disco usado (%)", [('100 * max by (mountpoint) (system_filesystem_utilization{mountpoint="/"})', "Disco raíz (/)")],
               32, 18, 16, 9, unit="percent", min_=0, max_=100),
        promql("CPU actual", [('100 * (1 - avg(system_cpu_utilization{state="idle"}))', "CPU")], 0, 27, 12, 7,
               unit="percent", kind="gauge", min_=0, max_=100),
        promql("RAM actual", [('100 * sum(system_memory_utilization{state="used"})', "RAM")], 12, 27, 12, 7,
               unit="percent", kind="gauge", min_=0, max_=100),
        promql("Tráfico de red total (MB/min)", [
            (f'(sum(rate(node_network_receive_bytes_total{{{NET}}}[5m])) + '
             f'sum(rate(node_network_transmit_bytes_total{{{NET}}}[5m]))) * 60 / 1048576', "Red")], 24, 27, 12, 7,
            unit="custom:MB/min", kind="metric"),
        promql("Procesos en ejecución", [("sum(system_processes_count)", "Procesos")], 36, 27, 12, 7, kind="metric", decimals=0),
    ], period="1h")


LOGS = '"default"'


def app_dashboard():
    return dashboard("Aplicación InvenTrack", "Peticiones por segundo, latencia, errores HTTP y statusCode por endpoint", [
        promql("Peticiones por segundo por endpoint",
               [("sum by (http_route) (rate(app_http_requests_total[2m]))", "{http_route}")], 0, 0, 24, 9,
               unit="custom:req/s"),
        promql("Latencia p95 por endpoint (ms)",
               [("histogram_quantile(0.95, sum by (le, http_route) (rate(app_http_request_duration_ms_bucket[5m])))",
                 "{http_route}")], 24, 0, 24, 9, unit="custom:ms"),
        promql("Tasa de error HTTP (%) por endpoint",
               [("clamp_max(100 * sum by (http_route) (increase(app_http_errors_total[5m])) / "
                 "sum by (http_route) (increase(app_http_requests_total[5m])), 100)", "{http_route}")], 0, 9, 24, 9,
               unit="percent"),
        sql("Respuestas por statusCode",
            f"SELECT histogram(_timestamp) AS x_axis_1, CAST(status_code AS VARCHAR) AS breakdown_1, "
            f"count(*) AS y_axis_1 FROM {LOGS} WHERE event = 'http_request' GROUP BY x_axis_1, breakdown_1 "
            f"ORDER BY x_axis_1", "default", "logs", ["x_axis_1"], ["y_axis_1"], ["breakdown_1"], 24, 9, 24, 9,
            kind="bar"),
        sql("Resumen por endpoint",
            f"SELECT http_method AS metodo, http_route AS endpoint, count(*) AS peticiones, "
            f"round(avg(duration_ms), 2) AS latencia_prom_ms, round(approx_percentile_cont(duration_ms, 0.95), 2) AS latencia_p95_ms, "
            f"sum(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) AS errores, max(_timestamp) AS ultimo "
            f"FROM {LOGS} WHERE event = 'http_request' GROUP BY metodo, endpoint ORDER BY peticiones DESC",
            "default", "logs", ["metodo", "endpoint"],
            ["peticiones", "latencia_prom_ms", "latencia_p95_ms", "errores", "ultimo"], [], 0, 18, 48, 10, kind="table"),
        sql("Latencia promedio (ms)",
            f"SELECT histogram(_timestamp) AS x_axis_1, round(avg(duration_ms), 2) AS y_axis_1 FROM {LOGS} "
            f"WHERE event = 'http_request' GROUP BY x_axis_1 ORDER BY x_axis_1", "default", "logs",
            ["x_axis_1"], ["y_axis_1"], [], 0, 28, 24, 8, kind="area", unit="custom:ms"),
        sql("Inicios de sesión",
            f"SELECT histogram(_timestamp) AS x_axis_1, event AS breakdown_1, count(*) AS y_axis_1 FROM {LOGS} "
            f"WHERE event IN ('login_ok', 'login_failed', 'login_inactive') GROUP BY x_axis_1, breakdown_1 "
            f"ORDER BY x_axis_1", "default", "logs", ["x_axis_1"], ["y_axis_1"], ["breakdown_1"], 24, 28, 24, 8,
            kind="bar"),
        sql("Últimos errores y excepciones",
            f"SELECT _timestamp AS hora, severity AS nivel, body AS mensaje, trace_id AS traza FROM {LOGS} "
            f"WHERE severity IN ('ERROR', 'WARN', 'WARNING') ORDER BY _timestamp DESC LIMIT 50",
            "default", "logs", ["hora"], ["nivel", "mensaje", "traza"], [], 0, 36, 48, 10, kind="table"),
    ])


def cicd_dashboard():
    s = '"cicd_pipeline"'
    return dashboard("CI/CD y alertas", "Ejecuciones de GitHub Actions, despliegues en EC2 y alertas disparadas", [
        sql("Ejecuciones del pipeline",
            f"SELECT timestamp AS fecha, event_type AS evento, status AS estado, branch AS rama, commit_short AS commit, "
            f"actor AS usuario, tests_passed AS aprobadas, tests_failed AS fallidas, message AS detalle, run_url AS ejecucion "
            f"FROM {s} ORDER BY _timestamp DESC LIMIT 100", "cicd_pipeline", "logs", ["fecha"],
            ["evento", "estado", "rama", "commit", "usuario", "aprobadas", "fallidas", "detalle", "ejecucion"], [],
            0, 0, 48, 11, kind="table"),
        sql("Resultados por estado",
            f"SELECT histogram(_timestamp, '1 hour') AS x_axis_1, concat(event_type, ' ', status) AS breakdown_1, "
            f"count(*) AS y_axis_1 FROM {s} GROUP BY x_axis_1, breakdown_1 ORDER BY x_axis_1",
            "cicd_pipeline", "logs", ["x_axis_1"], ["y_axis_1"], ["breakdown_1"], 0, 11, 24, 9, kind="bar"),
        sql("Despliegues exitosos", f"SELECT count(*) AS y_axis_1 FROM {s} WHERE event_type = 'deploy' AND status = 'success'",
            "cicd_pipeline", "logs", [], ["y_axis_1"], [], 24, 11, 12, 9, kind="metric", decimals=0),
        sql("Despliegues bloqueados", f"SELECT count(*) AS y_axis_1 FROM {s} WHERE event_type = 'deploy_blocked'",
            "cicd_pipeline", "logs", [], ["y_axis_1"], [], 36, 11, 12, 9, kind="metric", decimals=0),
        sql("Alertas disparadas",
            "SELECT _timestamp AS hora, alert_name AS alerta, severity AS severidad, detail AS detalle "
            "FROM \"alert_events\" ORDER BY _timestamp DESC LIMIT 50", "alert_events", "logs", ["hora"],
            ["alerta", "severidad", "detalle"], [], 0, 20, 48, 9, kind="table"),
    ], period="7d")


def clients_dashboard():
    """Experiencia por ubicación y dispositivo (datos que envía el navegador y simulación de clientes)."""
    api = f"FROM {LOGS} WHERE event = 'client_api'"
    return dashboard("Clientes y dispositivos (simulación)",
                     "Ubicación, zona horaria, dispositivo, red, CPU y GPU de los clientes; tiempo percibido frente al del servidor", [
        sql("Tiempo de respuesta percibido por ubicación (ms)",
            f"SELECT histogram(_timestamp) AS x_axis_1, client_location AS breakdown_1, round(avg(duration_ms), 1) AS y_axis_1 "
            f"{api} GROUP BY x_axis_1, breakdown_1 ORDER BY x_axis_1", "default", "logs",
            ["x_axis_1"], ["y_axis_1"], ["breakdown_1"], 0, 0, 24, 9, unit="custom:ms",
            labels={"y_axis_1": "ms percibidos", "breakdown_1": "Ubicación"},
            description="Lo que tarda cada llamada a la API vista desde el navegador: incluye la red del cliente"),
        sql("Peticiones por ubicación",
            f"SELECT histogram(_timestamp) AS x_axis_1, client_location AS breakdown_1, count(*) AS y_axis_1 "
            f"{api} GROUP BY x_axis_1, breakdown_1 ORDER BY x_axis_1", "default", "logs",
            ["x_axis_1"], ["y_axis_1"], ["breakdown_1"], 24, 0, 24, 9, kind="bar",
            labels={"y_axis_1": "Peticiones", "breakdown_1": "Ubicación"}),
        sql("Comparativa por ubicación",
            f"SELECT client_location AS ubicacion, max(client_timezone) AS zona_horaria, max(client_device) AS dispositivo, "
            f"count(*) AS peticiones, round(avg(duration_ms), 1) AS percibido_prom_ms, "
            f"round(approx_percentile_cont(duration_ms, 0.95), 1) AS percibido_p95_ms, "
            f"sum(CASE WHEN status_code >= 400 OR status_code = 0 THEN 1 ELSE 0 END) AS errores {api} "
            f"GROUP BY ubicacion ORDER BY percibido_prom_ms DESC", "default", "logs", ["ubicacion"],
            ["zona_horaria", "dispositivo", "peticiones", "percibido_prom_ms", "percibido_p95_ms", "errores"], [],
            0, 9, 48, 8, kind="table"),
        sql("Tiempo en el servidor por ubicación (ms)",
            f"SELECT client_location AS x_axis_1, round(avg(duration_ms), 1) AS y_axis_1 FROM {LOGS} "
            f"WHERE event = 'http_request' AND client_location != '' GROUP BY x_axis_1 ORDER BY x_axis_1",
            "default", "logs", ["x_axis_1"], ["y_axis_1"], [], 0, 17, 16, 9, kind="bar", unit="custom:ms",
            labels={"x_axis_1": "Ubicación", "y_axis_1": "ms en servidor"},
            description="Tiempo medido dentro de la EC2 (incluye recibir la petición por la red del cliente)"),
        sql("Carga de la página por ubicación (ms)",
            f"SELECT client_location AS x_axis_1, round(avg(ttfb_ms), 1) AS y_axis_1, round(avg(load_ms), 1) AS y_axis_2 "
            f"FROM {LOGS} WHERE event = 'client_page' GROUP BY x_axis_1 ORDER BY x_axis_1", "default", "logs",
            ["x_axis_1"], ["y_axis_1", "y_axis_2"], [], 16, 17, 16, 9, kind="bar", unit="custom:ms",
            labels={"x_axis_1": "Ubicación", "y_axis_1": "Primer byte (TTFB)", "y_axis_2": "Carga completa"},
            description="Primer byte (TTFB) y carga completa de la página en el navegador"),
        sql("CPU del dispositivo: prueba de cálculo (ms)",
            f"SELECT client_location AS x_axis_1, round(avg(cpu_bench_ms), 1) AS y_axis_1 FROM {LOGS} "
            f"WHERE event = 'client_device' GROUP BY x_axis_1 ORDER BY x_axis_1", "default", "logs",
            ["x_axis_1"], ["y_axis_1"], [], 32, 17, 16, 9, kind="bar", unit="custom:ms",
            labels={"x_axis_1": "Ubicación", "y_axis_1": "ms de la prueba"},
            description="Misma carga de cálculo en cada navegador: más milisegundos = CPU más lenta o más ocupada"),
        sql("Dispositivos detectados",
            f"SELECT client_location AS ubicacion, max(client_timezone) AS zona_horaria, max(client_local_time) AS hora_local, "
            f"max(client_device) AS dispositivo, max(client_screen) AS pantalla, max(client_cpu_cores) AS nucleos, "
            f"max(gpu) AS gpu, round(avg(cpu_bench_ms), 1) AS cpu_prueba_ms, max(long_tasks_ms) AS cpu_bloqueada_ms, "
            f"max(js_heap_mb) AS memoria_js_mb, max(client_lat) AS lat, max(client_lon) AS lon "
            f"FROM {LOGS} WHERE event = 'client_device' GROUP BY ubicacion ORDER BY ubicacion", "default", "logs",
            ["ubicacion"], ["zona_horaria", "hora_local", "dispositivo", "pantalla", "nucleos", "gpu", "cpu_prueba_ms",
                            "cpu_bloqueada_ms", "memoria_js_mb", "lat", "lon"], [], 0, 26, 48, 8, kind="table"),
        promql("CPU del servidor (%) durante la simulación",
               [('100 * (1 - avg(system_cpu_utilization{state="idle"}))', "CPU EC2")],
               0, 34, 24, 8, unit="percent", min_=0, max_=100),
        promql("RAM del servidor (%) durante la simulación",
               [('100 * sum(system_memory_utilization{state="used"})', "RAM EC2")],
               24, 34, 24, 8, unit="percent", min_=0, max_=100),
    ], period="1h")


# ------------------------------------------------------------------ alertas --- #
def upsert(base, body):
    """Actualiza (PUT) si ya existe; si no, crea (POST)."""
    st, res = call("PUT", f"{base}/{body['name']}", body)
    if st != 200:
        st, res = call("POST", base, body)
    return st, res


def destination():
    tpl = {"name": "registro_alertas", "isDefault": False, "type": "http",
           "body": json.dumps([{"alert_name": "{alert_name}", "severity": "{severity}", "stream": "{stream_name}",
                                "detail": "{alert_name}: {alert_count} coincidencias entre {alert_start_time} y {alert_end_time}",
                                "org": "{org_name}", "url": "{alert_url}"}])}
    print("plantilla:", upsert(f"/api/{ORG}/alerts/templates", tpl))
    dest = {"name": "registro_alertas", "type": "http", "url": f"{SELF_URL}/api/{ORG}/alert_events/_json",
            "method": "post", "skip_tls_verify": True, "template": "registro_alertas",
            "headers": {"Authorization": AUTH, "Content-Type": "application/json"}}
    print("destino:", upsert(f"/api/{ORG}/alerts/destinations", dest))


def alert(name, stream, stream_type, sql_query, threshold, period, frequency, description, operator=">=", severity="warning",
          promql_query=None):
    query_condition = {"type": "promql" if promql_query else "sql", "conditions": [], "sql": sql_query or "",
                       "promql": promql_query or "", "promql_condition": None, "aggregation": None,
                       "vrl_function": None, "search_event_type": None, "multi_time_range": []}
    if promql_query:
        query_condition["promql_condition"] = {"column": "value", "operator": operator, "value": threshold}
    body = {"name": name, "stream_type": stream_type, "stream_name": stream, "is_real_time": False,
            "query_condition": query_condition,
            "trigger_condition": {"period": period, "operator": ">=", "threshold": 1 if promql_query else threshold,
                                  "frequency": frequency, "frequency_type": "minutes", "silence": 5, "timezone": "UTC"},
            "destinations": ["registro_alertas"], "context_attributes": {"severity": severity},
            "enabled": True, "description": description, "row_template": ""}
    call("DELETE", f"/api/v2/{ORG}/alerts?name={name}")  # por si existe (versión nueva)
    call("DELETE", f"/api/{ORG}/{stream}/alerts/{name}?type={stream_type}")
    st, res = call("POST", f"/api/{ORG}/{stream}/alerts?type={stream_type}", body)
    print(f"alerta {name}: {st} {str(res)[:160]}")


def alerts():
    destination()
    alert("errores_5xx", "default", "logs",
          "SELECT count(*) AS total FROM \"default\" WHERE event = 'http_request' AND status_code >= 500 "
          "HAVING count(*) >= 1", 1, 5, 1,
          "Al menos una respuesta HTTP 5xx en los últimos 5 minutos", severity="critical")
    alert("ataque_login", "default", "logs",
          "SELECT count(*) AS total FROM \"default\" WHERE event = 'login_failed' HAVING count(*) >= 10", 1, 5, 1,
          "10 o más inicios de sesión fallidos en 5 minutos")
    alert("latencia_alta", "default", "logs",
          "SELECT http_route, avg(duration_ms) AS ms FROM \"default\" WHERE event = 'http_request' "
          "GROUP BY http_route HAVING avg(duration_ms) > 800", 1, 5, 1,
          "Algún endpoint con latencia promedio mayor a 800 ms en 5 minutos")
    alert("pipeline_fallido", "cicd_pipeline", "logs",
          "SELECT count(*) AS total FROM \"cicd_pipeline\" WHERE status IN ('failure', 'blocked') "
          "HAVING count(*) >= 1", 1, 10, 1,
          "Un pipeline falló o un despliegue fue bloqueado en los últimos 10 minutos", severity="critical")
    alert("cpu_alta", "system_cpu_utilization", "metrics", None, 80, 5, 1,
          "CPU del servidor arriba de 80 %", operator=">", severity="critical",
          promql_query='100 * (1 - avg(system_cpu_utilization{state="idle"}))')
    alert("ram_alta", "system_memory_utilization", "metrics", None, 85, 5, 1,
          "Memoria RAM del servidor arriba de 85 %", operator=">", severity="critical",
          promql_query='100 * sum(system_memory_utilization{state="used"})')


def ensure_streams():
    """Crea los streams de eventos con un registro inicial para que los tableros y alertas los encuentren."""
    now = int(time.time() * 1_000_000)
    call("POST", f"/api/{ORG}/alert_events/_json",
         [{"_timestamp": now, "alert_name": "configuracion", "severity": "info",
           "detail": "Registro de alertas inicializado por o2_setup.py"}])
    call("POST", f"/api/{ORG}/cicd_pipeline/_json",
         [{"_timestamp": now, "event_type": "setup", "status": "success", "message": "OpenObserve configurado",
           "branch": "", "commit_short": "", "actor": "o2_setup", "tests_passed": 0, "tests_failed": 0,
           "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "run_url": ""}])


def dashboards():
    OUT.mkdir(parents=True, exist_ok=True)
    st, existing = call("GET", f"/api/{ORG}/dashboards")
    items = existing.get("dashboards", []) if isinstance(existing, dict) else []
    for build, fname in ((infra_dashboard, "infraestructura_ec2.json"), (app_dashboard, "aplicacion.json"),
                         (cicd_dashboard, "cicd_alertas.json"), (clients_dashboard, "clientes_simulacion.json")):
        d = build()
        (OUT / fname).write_text(json.dumps(d, indent=2, ensure_ascii=False))
        for item in items:
            v = item.get("v5") or item.get("v4") or item.get("v3") or {}
            if v.get("title") == d["title"]:
                call("DELETE", f"/api/{ORG}/dashboards/{v.get('dashboardId')}?folder=default")
        st, res = call("POST", f"/api/{ORG}/dashboards?folder=default", d)
        print(f"tablero '{d['title']}': {st}")


if __name__ == "__main__":
    if not O2_PASSWORD:
        sys.exit("Define O2_PASSWORD (y O2_URL / O2_USER si no son los predeterminados)")
    for i in range(30):
        try:
            urllib.request.urlopen(f"{O2_URL}/healthz", timeout=5)
            break
        except Exception:  # noqa: BLE001
            print("Esperando a OpenObserve…")
            time.sleep(3)
    ensure_streams()
    time.sleep(2)
    dashboards()
    alerts()
    print("Listo.")
