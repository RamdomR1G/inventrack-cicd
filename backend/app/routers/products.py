"""CRUD de productos: cualquier usuario con sesión puede consultarlos y administrarlos."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Product, User
from ..schemas import ProductCreate, ProductOut, ProductUpdate
from ..security import current_user

router = APIRouter(prefix="/api/products", tags=["products"])
log = logging.getLogger("inventrack.products")

# Ordenamientos permitidos (un "-" al inicio indica descendente).
SORTS = {
    "id": Product.id.asc(), "-id": Product.id.desc(),
    "name": func.lower(Product.name).asc(), "-name": func.lower(Product.name).desc(),
    "price": Product.price.asc(), "-price": Product.price.desc(),
    "stock": Product.stock.asc(), "-stock": Product.stock.desc(),
}
SORT_PATTERN = "^(" + "|".join(k.replace("-", r"\-") for k in SORTS) + ")$"


def _get(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Producto no encontrado")
    return product


def _sku_taken(db: Session, sku: str, exclude_id: int | None = None) -> bool:
    q = select(Product.id).where(Product.sku == sku)
    if exclude_id is not None:
        q = q.where(Product.id != exclude_id)
    return db.scalar(q) is not None


@router.get("")
def list_products(q: str = Query("", max_length=100), category: str = Query("", max_length=60),
                  sort: str = Query("id", pattern=SORT_PATTERN),
                  skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
                  db: Session = Depends(get_db), _: User = Depends(current_user)):
    query = select(Product)
    if q.strip():
        like = f"%{q.strip().lower()}%"
        query = query.where(or_(func.lower(Product.name).like(like), func.lower(Product.sku).like(like),
                                func.lower(Product.description).like(like)))
    if category.strip():
        query = query.where(Product.category == category.strip())
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(SORTS[sort], Product.id).offset(skip).limit(limit)).all()
    return {"total": total, "items": [ProductOut.model_validate(p) for p in items]}


@router.get("/categories", response_model=list[str])
def categories(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return list(db.scalars(select(Product.category).distinct().order_by(Product.category)))


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return _get(db, product_id)


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(data: ProductCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    sku = data.sku.upper()
    if _sku_taken(db, sku):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un producto con ese SKU")
    product = Product(**(data.model_dump() | {"sku": sku, "name": data.name.strip(), "category": data.category.strip()}))
    db.add(product)
    db.commit()
    db.refresh(product)
    log.info("Producto creado", extra={"event": "product_created", "product_id": product.id, "by": user.id})
    return product


@router.put("/{product_id}", response_model=ProductOut)
def update_product(product_id: int, data: ProductUpdate, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    product = _get(db, product_id)
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    if "sku" in changes:
        changes["sku"] = changes["sku"].upper()
        if _sku_taken(db, changes["sku"], exclude_id=product_id):
            raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un producto con ese SKU")
    for key, value in changes.items():
        setattr(product, key, value.strip() if key in ("name", "category") else value)
    db.commit()
    db.refresh(product)
    log.info("Producto actualizado", extra={"event": "product_updated", "product_id": product.id, "by": user.id})
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    product = _get(db, product_id)
    db.delete(product)
    db.commit()
    log.info("Producto eliminado", extra={"event": "product_deleted", "product_id": product_id, "by": user.id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
