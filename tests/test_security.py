import os
import socket
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from app import pipeline, security
from app.jobs import store
from app.main import app


# ---------- 1. Validasi Skema (HTTPS) & Kredensial ----------

@pytest.mark.parametrize(
    "invalid_url",
    [
        "http://youtube.com/watch?v=dQw4w9WgXcQ",
        "file:///etc/passwd",
        "ftp://example.com/video.mp4",
        "javascript:alert(1)",
        "gopher://example.com/",
        "data:text/plain;base64,SGVsbG8=",
        "",
        "   ",
        "not-a-url",
    ],
)
def test_reject_non_https_and_invalid_schemes(invalid_url):
    with pytest.raises(security.SecurityValidationError):
        security.validate_video_url(invalid_url)


def test_reject_credentials_in_url():
    with pytest.raises(security.SecurityValidationError, match="kredensial"):
        security.validate_video_url("https://user:pass@www.youtube.com/watch?v=123")


def test_reject_non_standard_port():
    with pytest.raises(security.SecurityValidationError, match="Port"):
        security.validate_video_url("https://www.youtube.com:8443/watch?v=123")


# ---------- 2. SSRF Protection: Private IPs & Localhost ----------

@pytest.mark.parametrize(
    "private_url",
    [
        "https://127.0.0.1/video.mp4",
        "https://127.0.0.2/video.mp4",
        "https://10.0.0.1/video.mp4",
        "https://172.16.0.1/video.mp4",
        "https://172.31.255.254/video.mp4",
        "https://192.168.1.1/video.mp4",
        "https://169.254.169.254/latest/meta-data/",
        "https://0.0.0.0/video.mp4",
        "https://[::1]/video.mp4",
        "https://[fe80::1]/video.mp4",
        "https://[fc00::1]/video.mp4",
        "https://localhost/video.mp4",
        "https://localhost:8765/api/jobs",
    ],
)
def test_reject_private_ips_and_localhost(private_url):
    with pytest.raises(security.SecurityValidationError):
        security.validate_video_url(private_url)


def test_reject_domain_resolving_to_private_ip(monkeypatch):
    monkeypatch.setenv("ALLOWED_DOMAINS", "malicious-domain.com")
    # Simulasikan malicious-domain.com mengarah ke IP privat 127.0.0.1
    fake_addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]
    with patch("socket.getaddrinfo", return_value=fake_addrinfo):
        with pytest.raises(security.SecurityValidationError, match="IP privat atau localhost"):
            security.validate_video_url("https://malicious-domain.com/video.mp4")


def test_reject_failed_dns_resolution(monkeypatch):
    monkeypatch.setenv("ALLOWED_DOMAINS", "unreachable-test-domain.com")
    with patch("socket.getaddrinfo", side_effect=socket.gaierror("Name or service not known")):
        with pytest.raises(security.SecurityValidationError, match="resolusi DNS"):
            security.validate_video_url("https://unreachable-test-domain.com/video.mp4")


# ---------- 3. Domain Allowlist & Filtering ----------

@pytest.mark.parametrize(
    "untrusted_url",
    [
        "https://evil.com/video.mp4",
        "https://attacker.org/video.mp4",
        "https://fakeyoutube.com/watch?v=123",
        "https://youtube.com.attacker.com/watch?v=123",
        "https://1.1.1.1/video.mp4",
    ],
)
def test_reject_untrusted_domains(untrusted_url):
    with pytest.raises(security.SecurityValidationError, match="Domain .* tidak diizinkan|Penggunaan alamat IP langsung"):
        security.validate_video_url(untrusted_url)


@pytest.mark.parametrize(
    "valid_url,domain",
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "www.youtube.com"),
        ("https://youtu.be/dQw4w9WgXcQ", "youtu.be"),
        ("https://www.tiktok.com/@user/video/123456", "www.tiktok.com"),
        ("https://vimeo.com/12345678", "vimeo.com"),
    ],
)
def test_allow_verified_domains(valid_url, domain):
    fake_addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
    with patch("socket.getaddrinfo", return_value=fake_addrinfo):
        result = security.validate_video_url(valid_url)
        assert result == valid_url


def test_custom_allowed_domain_via_env(monkeypatch):
    monkeypatch.setenv("ALLOWED_DOMAINS", "my-organization-cdn.com, trusted-partner.org")
    fake_addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
    with patch("socket.getaddrinfo", return_value=fake_addrinfo):
        url = "https://media.my-organization-cdn.com/video.mp4"
        assert security.validate_video_url(url) == url


# ---------- 4. Resource Quotas (Filesize & Duration) ----------

def test_resource_quota_defaults():
    assert security.max_filesize_mb() == 500
    assert security.max_filesize_bytes() == 500 * 1024 * 1024
    assert security.max_duration_minutes() == 45
    assert security.max_duration_seconds() == 45 * 60


def test_resource_quota_custom_env(monkeypatch):
    monkeypatch.setenv("MAX_FILESIZE_MB", "250")
    monkeypatch.setenv("MAX_DURATION_MINUTES", "30")
    assert security.max_filesize_mb() == 250
    assert security.max_filesize_bytes() == 250 * 1024 * 1024
    assert security.max_duration_minutes() == 30
    assert security.max_duration_seconds() == 30 * 60


# ---------- 5. HTTP 400 Bad Request di API Endpoint ----------

def test_api_jobs_rejects_ssrf_and_private_ips():
    client = TestClient(app)

    # 1. AWS metadata link-local via http
    res1 = client.post("/api/jobs", data={"url": "http://169.254.169.254/latest/meta-data/"})
    assert res1.status_code == 400
    assert "https://" in res1.json()["detail"]

    # 2. AWS metadata link-local via https
    res2 = client.post("/api/jobs", data={"url": "https://169.254.169.254/latest/meta-data/"})
    assert res2.status_code == 400
    assert "IP privat" in res2.json()["detail"] or "tidak diizinkan" in res2.json()["detail"]

    # 3. Localhost internal port
    res3 = client.post("/api/jobs", data={"url": "http://localhost:8765/api/jobs"})
    assert res3.status_code == 400
    assert "https://" in res3.json()["detail"]

    # 4. Localhost internal port via https
    res4 = client.post("/api/jobs", data={"url": "https://localhost:8765/api/jobs"})
    assert res4.status_code == 400
    assert "Port" in res4.json()["detail"] or "host lokal" in res4.json()["detail"]

    # 5. Untrusted domain
    res5 = client.post("/api/jobs", data={"url": "https://attacker-domain.org/evil.mp4"})
    assert res5.status_code == 400
    assert "Domain" in res5.json()["detail"]


# ---------- 6. Safe Cancellation pada Durasi & Ukuran Berlebih ----------

def test_prepare_source_cancels_when_duration_exceeds_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(security, "max_duration_seconds", lambda: 1800)  # max 30 menit
    fake_video = tmp_path / "oversized_source.mp4"
    fake_video.write_bytes(b"\x00" * 100)

    job = {"id": "test-job-duration", "name": "test", "options": {}}
    store.jobs[job["id"]] = job

    # Mock media.probe agar mengembalikan durasi 3600 detik (60 menit)
    with patch("app.media.probe", return_value={"duration": 3600, "width": 1920, "height": 1080, "has_audio": True}):
        with pytest.raises(RuntimeError, match="Durasi video .* melebihi batas maksimum"):
            import asyncio
            asyncio.run(pipeline.prepare_source(job, fake_video, None))

    # Pastikan file yang melebihi batas otomatis dihapus secara aman
    assert not fake_video.exists()


def test_download_cleans_up_files_on_error(tmp_path, monkeypatch):
    job_id = "test-job-cleanup"
    job_dir = tmp_path / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    partial_file = job_dir / "source.mp4.part"
    partial_file.write_bytes(b"garbage partial download")

    monkeypatch.setattr(store, "dir", lambda jid: job_dir)

    # Ketika yt-dlp gagal / dibatalkan
    with patch("yt_dlp.YoutubeDL") as mock_ydl:
        mock_instance = MagicMock()
        mock_instance.__enter__.return_value = mock_instance
        mock_instance.extract_info.side_effect = RuntimeError("Unduhan dibatalkan karena kuota ukuran")
        mock_ydl.return_value = mock_instance

        job = {"id": job_id, "name": "test"}
        with pytest.raises(RuntimeError):
            pipeline._download(job, "https://www.youtube.com/watch?v=dummy", MagicMock())

    # Pastikan file sisa telah dibersihkan
    assert not partial_file.exists()
