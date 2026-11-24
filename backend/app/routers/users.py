"""CRUD de usuarios (solo administradores)."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..schemas import UserCreate, UserOut, UserUpdate
from ..security import admin_user, hash_password

router = APIRouter(prefix="/api/users", tags=["users"])
log = logging.getLogger("inventrack.users")


def _get(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    return user


def _email_taken(db: Session, email: str, exclude_id: int | None = None) -> bool:
    q = select(User.id).where(User.email == email)
    if exclude_id is not None:
        q = q.where(User.id != exclude_id)
    return db.scalar(q) is not None


@router.get("")
def list_users(q: str = Query("", max_length=100), skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
               db: Session = Depends(get_db), _: User = Depends(admin_user)):
    query = select(User)
    if q.strip():
        like = f"%{q.strip().lower()}%"
        query = query.where(or_(func.lower(User.name).like(like), User.email.like(like)))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(User.id).offset(skip).limit(limit)).all()
    return {"total": total, "items": [UserOut.model_validate(u) for u in items]}


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: int, db: Session = Depends(get_db), _: User = Depends(admin_user)):
    return _get(db, user_id)


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(data: UserCreate, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    email = data.email.lower()
    if _email_taken(db, email):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un usuario con ese correo")
    user = User(name=data.name.strip(), email=email, role=data.role, is_active=data.is_active,
                password_hash=hash_password(data.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    log.info("Usuario creado", extra={"event": "user_created", "user_id": user.id, "by": admin.id})
    return user


@router.put("/{user_id}", response_model=UserOut)
def update_user(user_id: int, data: UserUpdate, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    user = _get(db, user_id)
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    if "email" in changes:
        changes["email"] = changes["email"].lower()
        if _email_taken(db, changes["email"], exclude_id=user_id):
            raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un usuario con ese correo")
    if user.id == admin.id and (changes.get("role") == "user" or changes.get("is_active") is False):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No puedes quitarte el rol de administrador ni desactivarte")
    if "password" in changes:
        user.password_hash = hash_password(changes.pop("password"))
    if "name" in changes:
        changes["name"] = changes["name"].strip()
    for key, value in changes.items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    log.info("Usuario actualizado", extra={"event": "user_updated", "user_id": user.id, "by": admin.id})
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    user = _get(db, user_id)
    if user.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No puedes eliminar tu propio usuario")
    db.delete(user)
    db.commit()
    log.info("Usuario eliminado", extra={"event": "user_deleted", "user_id": user_id, "by": admin.id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
