"""Backend: endpoint que recibe las métricas del navegador (ubicación, dispositivo, CPU y tiempos)."""
import pytest

pytestmark = pytest.mark.api

CONTEXT = {"location": "pytest", "timezone": "America/Mexico_City", "utc_offset_min": -360,
           "local_time": "24/11/2026, 15:40:00", "locale": "es-MX", "device": "escritorio",
           "screen": "1920x1080", "cpu_cores": 8, "memory_gb": 8, "network": "4g", "user_agent": "pytest"}


def test_client_report_accepts_all_event_kinds(anon):
    events = [
        {"kind": "api", "method": "GET", "route": "/api/products", "status": 200, "ms": 84.5},
        {"kind": "page", "route": "/productos", "ttfb_ms": 40, "dom_ms": 310, "load_ms": 420},
        {"kind": "device", "cpu_bench_ms": 35.2, "long_tasks_ms": 0, "js_heap_mb": 12, "gpu": "SwiftShader"},
    ]
    r = anon.post("/api/telemetry/client", data={"context": CONTEXT, "events": events})
    assert r.status == 204


def test_client_report_does_not_require_session(anon):
    r = anon.post("/api/telemetry/client", data={"context": {"location": "tokio"}, "events": []})
    assert r.status == 204


def test_client_report_rejects_unknown_kind(anon):
    r = anon.post("/api/telemetry/client", data={"context": CONTEXT, "events": [{"kind": "otro"}]})
    assert r.status == 422


def test_client_report_rejects_oversized_batch(anon):
    events = [{"kind": "api", "method": "GET", "route": "/api/products", "status": 200, "ms": 1}] * 51
    r = anon.post("/api/telemetry/client", data={"context": CONTEXT, "events": events})
    assert r.status == 422


def test_client_report_rejects_negative_times(anon):
    r = anon.post("/api/telemetry/client", data={"context": CONTEXT,
                                                  "events": [{"kind": "page", "route": "/", "load_ms": -5}]})
    assert r.status == 422
