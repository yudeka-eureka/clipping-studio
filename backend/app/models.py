"""Model SQLAlchemy deklaratif untuk database Clipping Studio.

Menyediakan Base metadata untuk Alembic migrasi dan autogenerate,
serta representasi ORM untuk tabel users dan model_keys.
"""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.mysql import TIMESTAMP
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), nullable=False, unique=True)
    email = Column(String(100), nullable=False, unique=True)
    password = Column(String(255), nullable=False)
    credential_token = Column(String(255), nullable=False, unique=True)
    profile_photo = Column(String(500), nullable=True)
    username_changed_at = Column(TIMESTAMP, nullable=True)
    created_at = Column(TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(TIMESTAMP, server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"))

    model_keys = relationship("ModelKey", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} email={self.email!r}>"


class ModelKey(Base):
    __tablename__ = "model_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type = Column(String(30), nullable=False)
    provider = Column(String(50), nullable=False)
    key = Column(Text, nullable=False)
    secret_key = Column(Text, nullable=True)
    r2_account_id = Column(Text, nullable=True)
    r2_bucket = Column(String(255), nullable=True)
    r2_bucket_url = Column(String(255), nullable=True)
    cloud_name = Column(String(120), nullable=True)
    model = Column(String(100), nullable=True)
    is_active = Column(Boolean, server_default=text("0"), default=False)
    created_at = Column(TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(TIMESTAMP, server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"))

    user = relationship("User", back_populates="model_keys")

    __table_args__ = (
        UniqueConstraint("user_id", "type", "provider", name="uq_user_type_provider"),
        Index("idx_user_type", "user_id", "type"),
    )

    def __repr__(self) -> str:
        return f"<ModelKey id={self.id} user_id={self.user_id} type={self.type!r} provider={self.provider!r}>"
