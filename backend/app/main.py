"""InvenTrack API: inicio de sesión, CRUD de usuarios y CRUD de productos."""
import logging
import time
from contextlib import asynccontextmanager
from decimal import Decimal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError

from .config import settings
from .db import Base, SessionLocal, engine
from .models import Product, User
from .routers import auth, client_telemetry, products, users
from .security import hash_password
from .telemetry import MetricsMiddleware, setup_telemetry

log = logging.getLogger("inventrack")

SAMPLE_PRODUCTS = [
    ("LAP-001", "Laptop 14 pulgadas", "Cómputo", "Ryzen 5, 16 GB RAM, SSD 512 GB", Decimal("14999.00"), 12),
    ("MON-024", "Monitor 24 pulgadas", "Cómputo", "Panel IPS Full HD a 75 Hz", Decimal("2899.00"), 20),
    ("TEC-101", "Teclado mecánico", "Accesorios", "Switches rojos, distribución en español", Decimal("899.00"), 35),
    ("MOU-202", "Mouse inalámbrico", "Accesorios", "Óptico, 2.4 GHz, 1600 DPI", Decimal("349.50"), 60),
    ("AUD-303", "Audífonos Bluetooth", "Audio", "Cancelación de ruido, 30 h de batería", Decimal("1299.00"), 8),
    ("CAB-404", "Cable HDMI 2 m", "Accesorios", "HDMI 2.1, 8K", Decimal("189.00"), 4),
]


def _wait_for_db(retries: int = 40):
    for attempt in range(1, retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except OperationalError:
            log.warning("Esperando la base de datos (%s/%s)", attempt, retries, extra={"event": "db_wait"})
            time.sleep(2)
    raise RuntimeError("No fue posible conectar con la base de datos")


def _seed():
    """Crea el administrador inicial y un catálogo de ejemplo si la base está vacía."""
    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.email == settings.admin_email)) is None:
            db.add(User(name=settings.admin_name, email=settings.admin_email, role="admin",
                        password_hash=hash_password(settings.admin_password)))
            log.info("Administrador inicial creado", extra={"event": "seed", "email": settings.admin_email})
        if db.scalar(select(Product.id).limit(1)) is None:
            for sku, name, cat, desc, price, stock in SAMPLE_PRODUCTS:
                db.add(Product(sku=sku, name=name, category=cat, description=desc, price=price, stock=stock))
        db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _wait_for_db()
    Base.metadata.create_all(engine)
    _seed()
    log.info("InvenTrack API iniciada", extra={"event": "startup", "version": settings.app_version})
    yield


app = FastAPI(title="InvenTrack API", version=settings.app_version, lifespan=lifespan,
              docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(MetricsMiddleware)
setup_telemetry(app, engine)   # se agrega después: queda por fuera y el middleware corre dentro de la traza


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    errors = [{"field": str(e["loc"][1]) if len(e["loc"]) > 1 else str(e["loc"][0]), "message": e["msg"]}
              for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": "Datos inválidos", "errors": errors})


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": "Error interno del servidor"})


@app.get("/api/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "version": settings.app_version, "environment": settings.environment}


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(products.router)
app.include_router(client_telemetry.router)
