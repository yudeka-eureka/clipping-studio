"""Pengujian menyeluruh untuk modul database_preparation dan sistem migrasi Alembic."""
from __future__ import annotations

import asyncio
import json
import pytest
from app import db, database_preparation
from app.models import User, ModelKey, Base


@pytest.fixture(autouse=True)
def ensure_db_ready():
    """Pastikan database disiapkan dan berada pada revisi head sebelum setiap test."""
    db.init_db()


def test_ensure_database_exists():
    """Memastikan fungsi ensure_database_exists berjalan dengan baik."""
    ok = database_preparation.ensure_database_exists()
    assert ok is True


def test_get_alembic_config():
    """Memastikan get_alembic_config menghasilkan konfigurasi Alembic yang valid."""
    cfg = database_preparation.get_alembic_config()
    assert cfg is not None
    assert cfg.get_main_option("script_location") is not None
    assert "alembic" in cfg.get_main_option("script_location")


def test_alembic_migration_status():
    """Memastikan get_migration_status mengembalikan status seluruh revisi Alembic."""
    status_list = database_preparation.get_migration_status()
    assert len(status_list) >= 4

    versions = [m["version"] for m in status_list]
    assert versions[:4] == ["0001", "0002", "0003", "0004"]

    for item in status_list:
        assert "version" in item
        assert "name" in item
        assert "status" in item
        assert item["status"] in ("applied", "pending")
        assert item["status"] == "applied"
        assert item["description"] != ""


def test_run_migrations_idempotency():
    """Menjalankan run_migrations ketika sudah up to date harus mengembalikan list kosong (idempotent)."""
    newly_applied = database_preparation.run_migrations()
    assert newly_applied == []


def test_prepare_database_backward_compatibility():
    """Memastikan db.init_db() dan db.prepare_database() tetap berfungsi dengan baik."""
    assert db.prepare_database(raise_on_error=True) is True
    db.init_db()


def test_rollback_and_upgrade_cycle():
    """Menguji siklus rollback 1 langkah lalu upgrade kembali ke head."""
    # 1. Rollback 1 revisi (0004)
    rolled_back = database_preparation.rollback_migration(steps=1)
    assert len(rolled_back) == 1
    assert "0004" in rolled_back[0]

    # Cek status: 0004 harus pending
    status_after_rollback = database_preparation.get_migration_status()
    v_map = {s["version"]: s["status"] for s in status_after_rollback}
    assert v_map["0001"] == "applied"
    assert v_map["0002"] == "applied"
    assert v_map["0003"] == "applied"
    assert v_map["0004"] == "pending"

    # 2. Upgrade kembali ke head
    newly_applied = database_preparation.run_migrations()
    assert len(newly_applied) == 1
    assert "0004" in newly_applied[0]

    # Cek status: semua kembali applied
    status_after_upgrade = database_preparation.get_migration_status()
    assert all(s["status"] == "applied" for s in status_after_upgrade)


def test_target_version_migration():
    """Menguji migrasi ke versi target tertentu (downgrade & upgrade terarah)."""
    # Downgrade ke target 0002
    rolled_back = database_preparation.rollback_migration(target_version="0002")
    assert len(rolled_back) == 2
    assert any("0004" in r for r in rolled_back)
    assert any("0003" in r for r in rolled_back)

    status = database_preparation.get_migration_status()
    v_map = {s["version"]: s["status"] for s in status}
    assert v_map["0001"] == "applied"
    assert v_map["0002"] == "applied"
    assert v_map["0003"] == "pending"
    assert v_map["0004"] == "pending"

    # Upgrade bertahap ke target 0003
    applied_3 = database_preparation.run_migrations(target_version="0003")
    assert len(applied_3) == 1
    assert "0003" in applied_3[0]

    # Kembalikan penuh ke head
    applied_all = database_preparation.run_migrations()
    assert len(applied_all) == 1
    assert "0004" in applied_all[0]


def test_database_health_check():
    """Memastikan fungsi check_database_health mengembalikan data status yang benar."""
    health = database_preparation.check_database_health()
    assert health["ok"] is True
    assert health["database"] == "clipping_studio"
    assert health["applied_migrations"] >= 4
    assert health["pending_migrations"] == 0
    assert health["error"] is None


def test_ddl_helpers():
    """Pengujian helper DDL: table_exists, column_exists, index_exists, add_column, drop_column."""
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            # 1. table_exists
            assert database_preparation.table_exists(cur, "users") is True
            assert database_preparation.table_exists(cur, "non_existent_table_xyz") is False

            # 2. column_exists
            assert database_preparation.column_exists(cur, "users", "username") is True
            assert database_preparation.column_exists(cur, "users", "profile_photo") is True
            assert database_preparation.column_exists(cur, "users", "xyz_random_col") is False

            # 3. index_exists
            assert database_preparation.index_exists(cur, "model_keys", "idx_user_type") is True
            assert database_preparation.index_exists(cur, "model_keys", "non_existent_idx") is False

            # 4. add_column_if_not_exists (kolom baru)
            dummy_col = "test_col_temp_123"
            if database_preparation.column_exists(cur, "users", dummy_col):
                database_preparation.drop_column_if_exists(cur, "users", dummy_col)

            added = database_preparation.add_column_if_not_exists(cur, "users", dummy_col, "VARCHAR(100) NULL")
            assert added is True
            assert database_preparation.column_exists(cur, "users", dummy_col) is True

            # 5. add_column_if_not_exists (kolom sudah ada -> no-op)
            added_again = database_preparation.add_column_if_not_exists(cur, "users", dummy_col, "VARCHAR(100) NULL")
            assert added_again is False

            # 6. drop_column_if_exists
            dropped = database_preparation.drop_column_if_exists(cur, "users", dummy_col)
            assert dropped is True
            assert database_preparation.column_exists(cur, "users", dummy_col) is False

            # 7. drop_column_if_exists (kolom tidak ada -> no-op)
            dropped_again = database_preparation.drop_column_if_exists(cur, "users", dummy_col)
            assert dropped_again is False
    finally:
        conn.close()


def test_identifier_validation_security():
    """Memastikan _validate_identifier menolak karakter berbahaya yang berpotensi SQL injection."""
    assert database_preparation._validate_identifier("users") == "users"
    assert database_preparation._validate_identifier("model_keys_2") == "model_keys_2"

    with pytest.raises(ValueError):
        database_preparation._validate_identifier("users; DROP TABLE users;--")

    with pytest.raises(ValueError):
        database_preparation._validate_identifier("user name with spaces")

    with pytest.raises(ValueError):
        database_preparation._validate_identifier("users` WHERE 1=1")


def test_cli_migrate_handlers(capsys):
    """Menguji eksekusi perintah CLI migrate via cmd_migrate."""
    from app.cli import cmd_migrate, build_parser

    parser = build_parser()

    # 1. Status mode (text)
    args = parser.parse_args(["migrate", "--status"])
    asyncio.run(cmd_migrate(args))
    captured = capsys.readouterr()
    assert "Status Migrasi Database:" in captured.out
    assert "0001_create_users_table" in captured.out

    # 2. Status mode (json)
    args = parser.parse_args(["migrate", "--status", "--json"])
    asyncio.run(cmd_migrate(args))
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["ok"] is True
    assert len(data["migrations"]) >= 4

    # 3. Default run (ketika up to date)
    args = parser.parse_args(["migrate"])
    asyncio.run(cmd_migrate(args))
    captured = capsys.readouterr()
    assert "Database sudah up-to-date" in captured.out


def test_alembic_check_schema_synchronization():
    """Memastikan 'alembic check' berhasil tanpa diffs antara database dan model SQLAlchemy."""
    from alembic import command
    cfg = database_preparation.get_alembic_config()
    # command.check akan raise AutogenerateDiffsDetected jika ada ketidaksesuaian skema
    command.check(cfg)


def test_cli_migrate_target_and_rollback(capsys):
    """Menguji CLI migrate dengan --target dan --rollback --target."""
    from app.cli import cmd_migrate, build_parser

    parser = build_parser()

    # 1. Rollback ke target 0002 via --target
    args = parser.parse_args(["migrate", "--target", "0002"])
    asyncio.run(cmd_migrate(args))
    captured = capsys.readouterr()
    assert "Berhasil rollback ke versi 0002" in captured.out

    status = database_preparation.get_migration_status()
    v_map = {s["version"]: s["status"] for s in status}
    assert v_map["0002"] == "applied"
    assert v_map["0003"] == "pending"

    # 2. Upgrade ke target 0003
    args = parser.parse_args(["migrate", "--target", "0003"])
    asyncio.run(cmd_migrate(args))
    captured = capsys.readouterr()
    assert "Berhasil menerapkan migrasi ke 0003" in captured.out

    # 3. Upgrade kembali ke head
    args = parser.parse_args(["migrate"])
    asyncio.run(cmd_migrate(args))
    captured = capsys.readouterr()
    assert "0004" in captured.out or "Database sudah up-to-date" in captured.out


def test_prepare_database_custom_db_name():
    """Memastikan get_alembic_config dan database_preparation mendukung db_name kustom."""
    cfg = database_preparation.get_alembic_config(db_name="test_custom_db")
    url = cfg.get_main_option("sqlalchemy.url")
    assert "test_custom_db" in url


def test_sqlalchemy_models_declarative():
    """Memastikan model SQLAlchemy User dan ModelKey terdefinisi dengan benar pada metadata Base."""
    assert "users" in Base.metadata.tables
    assert "model_keys" in Base.metadata.tables

    user_tbl = Base.metadata.tables["users"]
    assert "id" in user_tbl.columns
    assert "username" in user_tbl.columns
    assert "email" in user_tbl.columns
    assert "credential_token" in user_tbl.columns
    assert "profile_photo" in user_tbl.columns
    assert "username_changed_at" in user_tbl.columns

    mk_tbl = Base.metadata.tables["model_keys"]
    assert "id" in mk_tbl.columns
    assert "user_id" in mk_tbl.columns
    assert "type" in mk_tbl.columns
    assert "provider" in mk_tbl.columns
    assert "key" in mk_tbl.columns
    assert "cloud_name" in mk_tbl.columns
    assert "model" in mk_tbl.columns
    assert "is_active" in mk_tbl.columns
