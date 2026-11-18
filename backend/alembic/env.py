"""Alembic environment script for Clipping Studio."""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool, create_engine
from alembic import context

# Pastikan folder backend masuk ke sys.path jika belum
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db import get_db_url
from app.models import Base

# Alembic Config object
config = context.config

# Konfigurasi logging jika fileConfig tersedia dan tidak diminta lewati
if config.config_file_name is not None and not config.attributes.get("skip_logging_config", False):
    try:
        fileConfig(config.config_file_name, disable_existing_loggers=False)
    except Exception:
        pass

# Metadata model SQLAlchemy untuk autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Jalankan migrasi dalam mode offline (menghasilkan SQL raw)."""
    url = config.get_main_option("sqlalchemy.url") or get_db_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Jalankan migrasi dalam mode online (terhubung langsung ke database)."""
    connection = config.attributes.get("connection", None)

    if connection is not None:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    else:
        url = config.get_main_option("sqlalchemy.url") or get_db_url()
        connectable = create_engine(url, poolclass=pool.NullPool)

        with connectable.connect() as conn:
            context.configure(
                connection=conn,
                target_metadata=target_metadata,
                compare_type=True,
                compare_server_default=True,
            )
            with context.begin_transaction():
                context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
