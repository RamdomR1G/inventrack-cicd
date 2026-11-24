"""Inicio de sesión y datos del usuario de la sesión."""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..schemas import LoginIn, TokenOut, UserOut
from ..security import create_token, current_user, verify_password
from ..telemetry import AUTH

router = APIRouter(prefix="/api/auth", tags=["auth"])
log = logging.getLogger("inventrack.auth")


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    email = data.email.lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(data.password, user.password_hash):
        AUTH.add(1, {"result": "failed"})
        log.warning("Inicio de sesión fallido", extra={"event": "login_failed", "email": email})
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Correo o contraseña incorrectos")
    if not user.is_active:
        AUTH.add(1, {"result": "inactive"})
        log.warning("Usuario inactivo intentó entrar", extra={"event": "login_inactive", "email": email})
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tu usuario está desactivado")
    AUTH.add(1, {"result": "ok"})
    log.info("Inicio de sesión correcto", extra={"event": "login_ok", "user_id": user.id})
    return TokenOut(access_token=create_token(user), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user
