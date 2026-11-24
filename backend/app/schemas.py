"""Esquemas de entrada y salida (validación con Pydantic)."""
from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Role = Literal["admin", "user"]
SKU = r"^[A-Za-z0-9\-_]+$"


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: str
    role: Role
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    role: Role = "user"
    is_active: bool = True


class UserUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=72)
    role: Optional[Role] = None
    is_active: Optional[bool] = None


class ProductCreate(BaseModel):
    sku: str = Field(min_length=3, max_length=40, pattern=SKU)
    name: str = Field(min_length=2, max_length=120)
    category: str = Field(default="General", min_length=2, max_length=60)
    description: str = Field(default="", max_length=1000)
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    stock: int = Field(default=0, ge=0, le=1_000_000)


class ProductUpdate(BaseModel):
    sku: Optional[str] = Field(default=None, min_length=3, max_length=40, pattern=SKU)
    name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    category: Optional[str] = Field(default=None, min_length=2, max_length=60)
    description: Optional[str] = Field(default=None, max_length=1000)
    price: Optional[Decimal] = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    stock: Optional[int] = Field(default=None, ge=0, le=1_000_000)


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sku: str
    name: str
    category: str
    description: str
    price: Decimal
    stock: int
    created_at: datetime
    updated_at: datetime
