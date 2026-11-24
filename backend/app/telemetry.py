"""Instrumentación OpenTelemetry (OTLP/HTTP) hacia el OpenTelemetry Collector → OpenObserve.

Emite las tres señales:
  * Trazas: FastAPI (cada petición) + SQLAlchemy (cada consulta) + spans propios.
  * Métricas: peticiones, errores y latencia por endpoint, método y statusCode.
  * Logs: un evento estructurado por petición y las excepciones, correlacionados con trace_id.
"""
import json
import logging
import time

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry._logs import set_logger_provider
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from .config import settings

log = logging.getLogger("inventrack")
_meter = metrics.get_meter("inventrack")

REQUESTS = _meter.create_counter(
    "app_http_requests_total", unit="1", description="Peticiones HTTP atendidas por endpoint")
ERRORS = _meter.create_counter(
    "app_http_errors_total", unit="1", description="Respuestas HTTP 4xx/5xx por endpoint")
LATENCY = _meter.create_histogram(
    "app_http_request_duration_ms", unit="ms", description="Latencia de las peticiones HTTP")
AUTH = _meter.create_counter(
    "app_login_attempts_total", unit="1", description="Intentos de inicio de sesión por resultado")


_STD = set(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    """Logs a stdout en JSON (además del envío OTLP) para `docker logs`."""

    def format(self, record):
        data = {"timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"), "level": record.levelname,
                "logger": record.name, "message": record.getMessage()}
        data.update({k: v for k, v in record.__dict__.items() if k not in _STD and not k.startswith("otel")})
        span = trace.get_current_span().get_span_context()
        if span.is_valid:
            data["trace_id"] = format(span.trace_id, "032x")
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False, default=str)


def setup_logging():
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        h = logging.StreamHandler()
        h.setFormatter(JsonFormatter())
        root.addHandler(h)
    logging.getLogger("uvicorn.access").disabled = True  # el middleware ya registra cada petición


def setup_telemetry(app, engine):
    setup_logging()
    if not settings.otel_enabled:
        log.info("OpenTelemetry deshabilitado (OTEL_SDK_DISABLED=true)")
        return
    resource = Resource.create({
        "service.name": settings.service_name,
        "service.version": settings.app_version,
        "deployment.environment": settings.environment,
    })
    base = settings.otlp_endpoint.rstrip("/")

    tp = TracerProvider(resource=resource)
    tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{base}/v1/traces")))
    trace.set_tracer_provider(tp)

    reader = PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=f"{base}/v1/metrics"),
                                           export_interval_millis=10_000)
    buckets = View(instrument_name="app_http_request_duration_ms",
                   aggregation=ExplicitBucketHistogramAggregation(
                       [5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000]))
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader], views=[buckets]))

    lp = LoggerProvider(resource=resource)
    lp.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter(endpoint=f"{base}/v1/logs")))
    set_logger_provider(lp)
    logging.getLogger().addHandler(LoggingHandler(level=logging.INFO, logger_provider=lp))

    FastAPIInstrumentor.instrument_app(app, excluded_urls="/api/health")
    SQLAlchemyInstrumentor().instrument(engine=engine, enable_commenter=False)
    log.info("OpenTelemetry habilitado", extra={"otlp_endpoint": base})


class MetricsMiddleware(BaseHTTPMiddleware):
    """Mide cada petición: latencia, conteo, errores y un log estructurado."""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        except Exception:
            log.exception("Excepción no controlada", extra={
                "event": "exception", "http_method": request.method, "url_path": request.url.path})
            raise
        finally:
            elapsed = (time.perf_counter() - start) * 1000
            route = request.scope.get("route")
            endpoint = getattr(route, "path", None) or request.url.path
            if endpoint.startswith("/api") and endpoint not in ("/api/health", "/api/telemetry/client"):
                attrs = {"http_method": request.method, "http_route": endpoint, "status_code": str(status)}
                REQUESTS.add(1, attrs)
                LATENCY.record(elapsed, attrs)
                if status >= 400:
                    ERRORS.add(1, attrs)
                level = logging.ERROR if status >= 500 else logging.WARNING if status >= 400 else logging.INFO
                log.log(level, f"{request.method} {endpoint} -> {status} ({elapsed:.1f} ms)", extra={
                    "event": "http_request", "http_method": request.method, "http_route": endpoint,
                    "url_path": request.url.path, "status_code": status, "duration_ms": round(elapsed, 2),
                    "client_ip": request.headers.get("x-real-ip") or (request.client.host if request.client else ""),
                    # Contexto que envía el navegador (ubicación lógica, dispositivo y zona horaria)
                    "client_location": request.headers.get("x-client-location", "")[:40],
                    "client_device": request.headers.get("x-client-device", "")[:20],
                    "client_timezone": request.headers.get("x-client-timezone", "")[:40],
                })
