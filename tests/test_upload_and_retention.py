import asyncio
import io
import os
import shutil
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from app import security
from app.jobs import store
from app.main import app


# ---------- 1. Magic Bytes / Header Video Validation ----------

@pytest.mark.parametrize(
    "header,expected_mime",
    [
        (b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41", "video/mp4"),
        (b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom", "video/mp4"),
        (b"\x00\x00\x00\x20ftypdash\x00\x00\x00\x00iso6mp41", "video/mp4"),
        (b"\x00\x00\x00\x14ftypqt  \x00\x00\x02\x00qt  ", "video/quicktime"),
        (b"\x00\x00\x00\x08wide\x00\x00\x03\xbe", "video/quicktime"),
        (b"\x00\x00\x00\x08moov\x00\x00\x01\x00", "video/quicktime"),
        (b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81\x01\x42\x82\x84webm\x42\x87", "video/webm"),
        (b"\x1a\x45\xdf\xa3\xa3\x42\x86\x81\x01\x42\x82\x88matroska\x42", "video/x-matroska"),
    ],
)
def test_detect_video_mime_valid_containers(header, expected_mime):
    assert security.detect_video_mime(header) == expected_mime
    assert security.validate_video_header(header) == expected_mime


@pytest.mark.parametrize(
    "bad_header",
    [
        b"#!/bin/bash\nrm -rf /",
        b"#!/usr/bin/env python3\nimport os",
        b"\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00",  # ELF binary
        b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff",        # PE binary
        b"<!DOCTYPE html><html><head></head>",
        b"%PDF-1.5\n%\xe2\xe3\xcf\xd3",
        b"PK\x03\x04\x14\x00\x00\x00\x08\x00",
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",                        # PNG image
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01",                      # JPEG image
        b"RIFF\x24\x00\x00\x00WEBPVP8 ",                               # WebP image
        b"GIF89a\x01\x00\x01\x00",
        b"",
        b"\x00\x01\x02\x03",
        b"random string that is not video",
    ],
)
def test_detect_video_mime_rejects_non_video_payloads(bad_header):
    assert security.detect_video_mime(bad_header) is None
    with pytest.raises(security.SecurityValidationError):
        security.validate_video_header(bad_header)


# ---------- 2. Upload Sanitization API Tests ----------

def test_api_upload_rejects_disallowed_extension():
    client = TestClient(app)
    fake_file = io.BytesIO(b"#!/bin/bash\necho bad")
    res = client.post(
        "/api/jobs",
        files={"file": ("malicious.sh", fake_file, "application/x-sh")},
    )
    assert res.status_code == 400
    assert "tidak didukung" in res.json()["detail"]


def test_api_upload_rejects_fake_extension_with_malicious_content(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "jobs")
    (tmp_path / "jobs").mkdir(parents=True, exist_ok=True)

    client = TestClient(app)
    # File bernama .mp4 tetapi isinya executable ELF
    fake_elf = io.BytesIO(b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 1024)
    res = client.post(
        "/api/jobs",
        files={"file": ("exploit.mp4", fake_elf, "video/mp4")},
    )
    assert res.status_code == 400
    assert "bukan format video yang valid" in res.json()["detail"]

    # Pastikan tidak ada job atau direktori yang tertinggal
    assert len(list((tmp_path / "jobs").glob("*"))) == 0 or all(
        p.name.startswith(".") for p in (tmp_path / "jobs").glob("*")
    )
    assert not any(j["name"] == "exploit.mp4" for j in store.jobs.values())


def test_api_upload_rejects_oversized_file(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "jobs")
    (tmp_path / "jobs").mkdir(parents=True, exist_ok=True)

    # Set batas maksimum menjadi 1 MB
    monkeypatch.setattr(security, "max_filesize_mb", lambda: 1)
    monkeypatch.setattr(security, "max_filesize_bytes", lambda: 1 * 1024 * 1024)

    # Buat file video valid (header ftypisom) tetapi ukurannya 2 MB (> 1 MB)
    header = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41"
    oversized_data = header + b"\x00" * (2 * 1024 * 1024)
    fake_file = io.BytesIO(oversized_data)

    client = TestClient(app)
    res = client.post(
        "/api/jobs",
        files={"file": ("oversized.mp4", fake_file, "video/mp4")},
    )
    assert res.status_code == 400
    assert "melebihi batas maksimum" in res.json()["detail"]

    # Pastikan tidak ada folder job yang tersimpan di disk
    job_folders = [p for p in (tmp_path / "jobs").iterdir() if not p.name.startswith(".")]
    assert len(job_folders) == 0
    assert not any(j["name"] == "oversized.mp4" for j in store.jobs.values())


def test_api_upload_accepts_valid_video(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "jobs")
    (tmp_path / "jobs").mkdir(parents=True, exist_ok=True)

    # Mock pipeline.run agar tidak menjalankan ffprobe/whisper sungguhan saat unit test
    with patch("app.pipeline.run", return_value=None):
        valid_video_data = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41" + b"\x00" * 4096
        fake_file = io.BytesIO(valid_video_data)

        client = TestClient(app)
        res = client.post(
            "/api/jobs",
            files={"file": ("good_video.mp4", fake_file, "video/mp4")},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["name"] == "good_video.mp4"
        assert data["source_type"] == "upload"

        # File source.mp4 harus tersimpan di direktori job
        dest_file = tmp_path / "jobs" / data["id"] / "source.mp4"
        assert dest_file.is_file()
        assert dest_file.stat().st_size == len(valid_video_data)

        # Bersihkan dari store
        store.jobs.pop(data["id"], None)


# ---------- 3. TTL / Retention Auto-Purge Tests ----------

def test_job_retention_defaults_and_env(monkeypatch):
    monkeypatch.delenv("JOB_RETENTION_HOURS", raising=False)
    assert security.job_retention_hours() == 24
    assert security.job_retention_seconds() == 24 * 3600

    monkeypatch.setenv("JOB_RETENTION_HOURS", "48")
    assert security.job_retention_hours() == 48
    assert security.job_retention_seconds() == 48 * 3600


def test_purge_expired_deletes_old_jobs(tmp_path, monkeypatch):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(store, "DATA_DIR", jobs_dir)

    now = time.time()
    # Job 1: Dibuat 30 jam yang lalu (kedaluwarsa jika retensi 24 jam)
    old_job_id = "job-old-expired"
    old_dir = jobs_dir / old_job_id
    old_dir.mkdir()
    (old_dir / "source.mp4").write_bytes(b"old video")
    old_job = {
        "id": old_job_id,
        "name": "Old Expired Video",
        "created_at": now - (30 * 3600),
        "status": "done",
        "clips": [],
    }
    store.jobs[old_job_id] = old_job

    # Job 2: Dibuat 2 jam yang lalu (masih aktif/baru)
    new_job_id = "job-recent"
    new_dir = jobs_dir / new_job_id
    new_dir.mkdir()
    (new_dir / "source.mp4").write_bytes(b"new video")
    new_job = {
        "id": new_job_id,
        "name": "Recent Video",
        "created_at": now - (2 * 3600),
        "status": "done",
        "clips": [],
    }
    store.jobs[new_job_id] = new_job

    # Jalankan pembersihan dengan retensi 24 jam (86400 detik)
    purged = asyncio.run(store.purge_expired(retention_seconds=24 * 3600))

    assert old_job_id in purged
    assert new_job_id not in purged

    # Direktori job lama harus terhapus
    assert not old_dir.exists()
    assert old_job_id not in store.jobs

    # Direktori job baru harus tetap ada
    assert new_dir.exists()
    assert new_job_id in store.jobs

    # Bersihkan
    store.jobs.pop(new_job_id, None)


def test_purge_expired_deletes_orphaned_directories(tmp_path, monkeypatch):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(store, "DATA_DIR", jobs_dir)

    # Buat direktori yang tidak tercatat di store.jobs dan set mtime ke masa lampau
    orphan_dir = jobs_dir / "orphaned-legacy-job"
    orphan_dir.mkdir()
    (orphan_dir / "garbage.mp4").write_bytes(b"garbage")
    past_time = time.time() - (50 * 3600)
    os.utime(orphan_dir, (past_time, past_time))

    purged = asyncio.run(store.purge_expired(retention_seconds=24 * 3600))

    assert "orphaned-legacy-job" in purged
    assert not orphan_dir.exists()


def test_purge_expired_cleans_stale_tmp_uploads(tmp_path, monkeypatch):
    jobs_dir = tmp_path / "jobs"
    tmp_uploads = jobs_dir / ".tmp_uploads"
    tmp_uploads.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(store, "DATA_DIR", jobs_dir)

    stale_file = tmp_uploads / "upload_stale.mp4"
    stale_file.write_bytes(b"stale partial upload")
    old_time = time.time() - 7200  # 2 jam yang lalu
    os.utime(stale_file, (old_time, old_time))

    fresh_file = tmp_uploads / "upload_fresh.mp4"
    fresh_file.write_bytes(b"in progress upload")

    asyncio.run(store.purge_expired(retention_seconds=24 * 3600))

    assert not stale_file.exists()
    assert fresh_file.exists()

    assert not stale_file.exists()
    assert fresh_file.exists()


def test_api_config_exposes_retention_hours():
    client = TestClient(app)
    res = client.get("/api/config")
    assert res.status_code == 200
    data = res.json()
    assert "job_retention_hours" in data
    assert data["job_retention_hours"] >= 1
