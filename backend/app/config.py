"""Configuración de InvenTrack leída de variables de entorno (ver .env.example)."""
import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: _env(
        "DATABASE_URL", "postgresql+psycopg://inventrack:inventrack@localhost:5432/inventrack"))
    jwt_secret: str = field(default_factory=lambda: _env("JWT_SECRET", "cambia-este-secreto"))
    jwt_minutes: int = field(default_factory=lambda: int(_env("JWT_MINUTES", "480")))

    admin_name: str = field(default_factory=lambda: _env("ADMIN_NAME", "Administrador"))
    admin_email: str = field(default_factory=lambda: _env("ADMIN_EMAIL", "admin@inventrack.com").lower())
    admin_password: str = field(default_factory=lambda: _env("ADMIN_PASSWORD", "Admin123*"))

    app_version: str = field(default_factory=lambda: _env("APP_VERSION", "dev"))
    environment: str = field(default_factory=lambda: _env("APP_ENV", "local"))

    # OpenTelemetry: se exporta por OTLP/HTTP al collector, que reenvía a OpenObserve.
    otel_enabled: bool = field(default_factory=lambda: _env("OTEL_SDK_DISABLED", "false").lower() != "true")
    service_name: str = field(default_factory=lambda: _env("OTEL_SERVICE_NAME", "inventrack-api"))
    otlp_endpoint: str = field(default_factory=lambda: _env("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"))


settings = Settings()
