"""Modul database preparation dan sistem migrasi skema database MySQL berbasis Alembic.

Memisahkan persiapan database dan eksekusi migrasi skema dari db.py agar
manajemen koneksi, persiapan environment, dan evolusi skema terkelola secara modular,
standar, dan aman untuk proyek FastAPI.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import pymysql
import pymysql.cursors
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, pool

ROOT_DIR = Path(__file__).resolve().parent.parent
ALEMBIC_INI = ROOT_DIR / "alembic.ini"
ALEMBIC_DIR = ROOT_DIR / "alembic"
IDENTIFIER_REGEX = re.compile(r"^[a-zA-Z0-9_]+$")


def _validate_identifier(name: str, kind: str = "identifier") -> str:
    cleaned = (name or "").strip()
    if not IDENTIFIER_REGEX.match(cleaned):
        raise ValueError(
            f"Nama {kind} tidak valid ('{name}'). Hanya huruf, angka, dan underscore yang diperbolehkan."
        )
    return cleaned


# Server and target database connection

def get_server_connection(connect_timeout: int = 5) -> pymysql.connections.Connection:
    """Buat koneksi ke server MySQL tanpa memilih database tertentu.

    Berguna untuk operasi tingkat server seperti CREATE DATABASE IF NOT EXISTS.
    """
    from .db import get_db_config

    config = get_db_config().copy()
    config.pop("database", None)
    config["connect_timeout"] = connect_timeout
    return pymysql.connect(**config)


def ensure_database_exists(db_name: str | None = None) -> bool:
    """Pastikan database target sudah ada di server MySQL.

    Jika belum ada, buat database dengan karakter set utf8mb4.
    Mengembalikan True jika database ada/berhasil dibuat, atau False jika gagal.
    """
    from .db import get_db_config

    target_db = db_name or get_db_config().get("database", "clipping_studio")
    valid_name = _validate_identifier(target_db, "database")

    try:
        conn = get_server_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{valid_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
                )
            return True
        finally:
            conn.close()
    except Exception as e:
        print(f"⚠️ [Database Prep] Peringatan saat memastikan database '{valid_name}': {e}")
        return False


# Schema inspection and DDL helpers

def table_exists(cur: pymysql.cursors.Cursor, table_name: str, db_name: str | None = None) -> bool:
    """Periksa apakah tabel ada di database saat ini."""
    t_name = _validate_identifier(table_name, "table")
    if db_name:
        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM information_schema.tables
            WHERE table_schema = %s AND table_name = %s
            """,
            (db_name, t_name),
        )
    else:
        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM information_schema.tables
            WHERE table_schema = DATABASE() AND table_name = %s
            """,
            (t_name,),
        )
    row = cur.fetchone()
    count = row["cnt"] if isinstance(row, dict) else row[0]
    return count > 0


def column_exists(cur: pymysql.cursors.Cursor, table_name: str, column_name: str, db_name: str | None = None) -> bool:
    """Periksa apakah kolom tertentu ada pada tabel."""
    t_name = _validate_identifier(table_name, "table")
    c_name = _validate_identifier(column_name, "column")
    if db_name:
        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s AND column_name = %s
            """,
            (db_name, t_name, c_name),
        )
    else:
        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM information_schema.columns
            WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s
            """,
            (t_name, c_name),
        )
    row = cur.fetchone()
    count = row["cnt"] if isinstance(row, dict) else row[0]
    return count > 0


def index_exists(cur: pymysql.cursors.Cursor, table_name: str, index_name: str, db_name: str | None = None) -> bool:
    """Periksa apakah index ada pada tabel."""
    t_name = _validate_identifier(table_name, "table")
    i_name = _validate_identifier(index_name, "index")
    if db_name:
        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM information_schema.statistics
            WHERE table_schema = %s AND table_name = %s AND index_name = %s
            """,
            (db_name, t_name, i_name),
        )
    else:
        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM information_schema.statistics
            WHERE table_schema = DATABASE() AND table_name = %s AND index_name = %s
            """,
            (t_name, i_name),
        )
    row = cur.fetchone()
    count = row["cnt"] if isinstance(row, dict) else row[0]
    return count > 0


def add_column_if_not_exists(
    cur: pymysql.cursors.Cursor,
    table_name: str,
    column_name: str,
    column_definition: str,
    db_name: str | None = None,
) -> bool:
    """Tambahkan kolom ke tabel hanya jika kolom tersebut belum ada."""
    t_name = _validate_identifier(table_name, "table")
    c_name = _validate_identifier(column_name, "column")
    if not column_exists(cur, t_name, c_name, db_name=db_name):
        cur.execute(f"ALTER TABLE `{t_name}` ADD COLUMN `{c_name}` {column_definition};")
        return True
    return False


def drop_column_if_exists(
    cur: pymysql.cursors.Cursor,
    table_name: str,
    column_name: str,
    db_name: str | None = None,
) -> bool:
    """Hapus kolom dari tabel hanya jika kolom tersebut ada."""
    t_name = _validate_identifier(table_name, "table")
    c_name = _validate_identifier(column_name, "column")
    if column_exists(cur, t_name, c_name, db_name=db_name):
        cur.execute(f"ALTER TABLE `{t_name}` DROP COLUMN `{c_name}`;")
        return True
    return False


def drop_table_if_exists(cur: pymysql.cursors.Cursor, table_name: str) -> bool:
    """Hapus tabel jika ada."""
    t_name = _validate_identifier(table_name, "table")
    if table_exists(cur, t_name):
        cur.execute(f"DROP TABLE IF EXISTS `{t_name}`;")
        return True
    return False


# Alembic migration engine

def get_alembic_config(
    config_path: str | Path | None = None,
    script_location: str | Path | None = None,
    db_name: str | None = None,
) -> Config:
    """Dapatkan objek Alembic Config yang siap pakai dengan path absolut yang valid."""
    from .db import get_db_url

    ini_path = Path(config_path) if config_path else ALEMBIC_INI
    if not ini_path.exists():
        raise FileNotFoundError(f"File konfigurasi Alembic tidak ditemukan: {ini_path}")

    cfg = Config(str(ini_path))
    scripts_dir = Path(script_location) if script_location else ALEMBIC_DIR
    cfg.set_main_option("script_location", str(scripts_dir))
    url = get_db_url(db_name=db_name)
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    cfg.attributes["skip_logging_config"] = True
    return cfg


def _get_applied_revisions(cfg: Config) -> list[str]:
    """Ambil daftar seluruh revision ID yang sudah pernah diterapkan ke database."""
    from .db import get_db_url

    script = ScriptDirectory.from_config(cfg)
    url = cfg.get_main_option("sqlalchemy.url") or get_db_url()
    engine = create_engine(url, poolclass=pool.NullPool)

    try:
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            current_heads = ctx.get_current_heads()
            if not current_heads:
                return []

            # Telusuri seluruh ancestry head untuk mengumpulkan seluruh revisi yang diterapkan
            applied: set[str] = set()
            for head in current_heads:
                for rev in script.walk_revisions(base=None, head=head):
                    applied.add(rev.revision)

            # Kembalikan dalam urutan kronologis
            all_revs = list(script.walk_revisions())
            all_revs.reverse()
            return [r.revision for r in all_revs if r.revision in applied]
    finally:
        engine.dispose()


def get_migration_status(
    db_name: str | None = None,
    config: Config | None = None,
) -> list[dict[str, Any]]:
    """Ambil status perbandingan seluruh migrasi Alembic (applied vs pending)."""
    cfg = config or get_alembic_config(db_name=db_name)
    script = ScriptDirectory.from_config(cfg)

    applied_set = set(_get_applied_revisions(cfg))
    all_revs = list(script.walk_revisions())
    all_revs.reverse()

    results: list[dict[str, Any]] = []
    for r in all_revs:
        is_applied = r.revision in applied_set
        desc = (r.doc or "").strip().splitlines()[0] if r.doc else ""
        name = f"{r.revision}_{desc.lower().replace(' ', '_')}" if desc else r.revision
        results.append({
            "version": r.revision,
            "name": name,
            "status": "applied" if is_applied else "pending",
            "applied_at": None,
            "description": desc,
        })
    return results


def run_migrations(
    target_version: str | None = None,
    db_name: str | None = None,
    config: Config | None = None,
) -> list[str]:
    """Jalankan migrasi yang belum diterapkan hingga target_version (default 'head').

    Mengembalikan daftar nama migrasi yang baru saja berhasil diterapkan.
    """
    cfg = config or get_alembic_config(db_name=db_name)
    script = ScriptDirectory.from_config(cfg)

    before_applied = set(_get_applied_revisions(cfg))
    target = target_version or "head"

    command.upgrade(cfg, target)

    after_applied = set(_get_applied_revisions(cfg))

    # Temukan nama migrasi baru yang diterapkan
    all_revs = list(script.walk_revisions())
    all_revs.reverse()
    newly_applied: list[str] = []
    for r in all_revs:
        if r.revision in after_applied and r.revision not in before_applied:
            desc = (r.doc or "").strip().splitlines()[0] if r.doc else ""
            name = f"{r.revision}_{desc.lower().replace(' ', '_')}" if desc else r.revision
            newly_applied.append(name)

    return newly_applied


def rollback_migration(
    steps: int = 1,
    target_version: str | None = None,
    db_name: str | None = None,
    config: Config | None = None,
) -> list[str]:
    """Rollback sejumlah `steps` migrasi terakhir, atau hingga target_version tertentu.

    Mengembalikan daftar nama migrasi yang berhasil di-rollback.
    """
    cfg = config or get_alembic_config(db_name=db_name)
    script = ScriptDirectory.from_config(cfg)

    applied_before = _get_applied_revisions(cfg)
    if not applied_before:
        return []

    if target_version is not None:
        target = target_version
    else:
        if steps >= len(applied_before):
            target = "base"
        else:
            target = f"-{max(1, steps)}"

    command.downgrade(cfg, target)

    after_applied = set(_get_applied_revisions(cfg))

    # Identifikasi migrasi yang ter-rollback
    all_revs = list(script.walk_revisions())
    all_revs.reverse()
    rolled_back: list[str] = []
    for r in all_revs:
        if r.revision in applied_before and r.revision not in after_applied:
            desc = (r.doc or "").strip().splitlines()[0] if r.doc else ""
            name = f"{r.revision}_{desc.lower().replace(' ', '_')}" if desc else r.revision
            rolled_back.append(name)

    return rolled_back


# Entry point and health check

def prepare_database(
    raise_on_error: bool = False,
    db_name: str | None = None,
    config: Config | None = None,
) -> bool:
    """Persiapkan database dan terapkan seluruh migrasi Alembic yang belum ada.

    1. Memastikan database target sudah dibuat di server MySQL.
    2. Menjalankan migrasi Alembic hingga revisi 'head'.
    """
    try:
        # 1. Pastikan database target ada
        ensure_database_exists(db_name=db_name)

        # 2. Jalankan migrasi Alembic ke head
        run_migrations(db_name=db_name, config=config)
        return True
    except Exception as e:
        if raise_on_error:
            raise
        print(f"⚠️ [Database Prep] Peringatan koneksi atau migrasi database: {e}")
        return False


def check_database_health(
    db_name: str | None = None,
    config: Config | None = None,
) -> dict[str, Any]:
    """Periksa status kesehatan koneksi database MySQL dan migrasi skema Alembic."""
    from .db import get_db_config

    cfg = get_db_config()
    target_db = db_name or cfg.get("database", "clipping_studio")
    try:
        status = get_migration_status(db_name=target_db, config=config)
        applied = sum(1 for s in status if s["status"] == "applied")
        pending = sum(1 for s in status if s["status"] == "pending")
        return {
            "ok": True,
            "database": target_db,
            "host": cfg.get("host"),
            "port": cfg.get("port"),
            "applied_migrations": applied,
            "pending_migrations": pending,
            "error": None,
        }
    except Exception as e:
        return {
            "ok": False,
            "database": target_db,
            "host": cfg.get("host"),
            "port": cfg.get("port"),
            "applied_migrations": 0,
            "pending_migrations": 0,
            "error": str(e),
        }


def init_db() -> None:
    """Wrapper kompatibilitas ke belakang untuk memanggil prepare_database."""
    prepare_database(raise_on_error=False)
