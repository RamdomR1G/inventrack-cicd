"""Recibe las métricas que mide el navegador (ubicación, dispositivo, red, CPU y tiempos percibidos)
y las registra como logs estructurados para OpenObserve.

No requiere sesión: la pantalla de login también reporta su tiempo de carga. Solo se aceptan
lotes pequeños con campos acotados, y nunca se guarda en la base de datos.
"""
import logging
from typing import Literal, Optional

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])
log = logging.getLogger("inventrack.client")


class ClientContext(BaseModel):
    location: str = Field(default="", max_length=40)
    timezone: str = Field(default="", max_length=40)
    utc_offset_min: int = Field(default=0, ge=-900, le=900)
    local_time: str = Field(default="", max_length=40)
    locale: str = Field(default="", max_length=20)
    device: str = Field(default="", max_length=20)
    screen: str = Field(default="", max_length=20)
    cpu_cores: int = Field(default=0, ge=0, le=512)
    memory_gb: float = Field(default=0, ge=0, le=1024)
    network: str = Field(default="", max_length=20)
    user_agent: str = Field(default="", max_length=200)
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lon: Optional[float] = Field(default=None, ge=-180, le=180)


class ClientEvent(BaseModel):
    kind: Literal["api", "page", "device"]
    method: Optional[str] = Field(default=None, max_length=10)
    route: Optional[str] = Field(default=None, max_length=120)
    status: Optional[int] = Field(default=None, ge=0, le=599)
    ms: Optional[float] = Field(default=None, ge=0, le=600_000)
    ttfb_ms: Optional[float] = Field(default=None, ge=0, le=600_000)
    dom_ms: Optional[float] = Field(default=None, ge=0, le=600_000)
    load_ms: Optional[float] = Field(default=None, ge=0, le=600_000)
    cpu_bench_ms: Optional[float] = Field(default=None, ge=0, le=600_000)
    long_tasks_ms: Optional[float] = Field(default=None, ge=0, le=86_400_000)
    js_heap_mb: Optional[float] = Field(default=None, ge=0, le=100_000)
    gpu: Optional[str] = Field(default=None, max_length=120)


class ClientReport(BaseModel):
    context: ClientContext
    events: list[ClientEvent] = Field(max_length=50)


@router.post("/client", status_code=status.HTTP_204_NO_CONTENT)
def client_report(report: ClientReport, request: Request):
    ctx = {f"client_{k}": v for k, v in report.context.model_dump().items() if v is not None}
    ctx["client_ip"] = request.headers.get("x-real-ip") or (request.client.host if request.client else "")
    for event in report.events:
        data = {k: v for k, v in event.model_dump().items() if v is not None and k != "kind"}
        if event.kind == "api":
            data = {"http_method": data.get("method"), "http_route": data.get("route"),
                    "status_code": data.get("status"), "duration_ms": data.get("ms")}
            message = f"[{report.context.location}] {event.method} {event.route} -> {event.status} ({event.ms} ms percibidos)"
        elif event.kind == "page":
            message = f"[{report.context.location}] carga de {event.route}: {event.load_ms} ms"
        else:
            message = f"[{report.context.location}] dispositivo: CPU {event.cpu_bench_ms} ms, GPU {event.gpu}"
        log.info(message, extra={"event": f"client_{event.kind}", **ctx, **data})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
