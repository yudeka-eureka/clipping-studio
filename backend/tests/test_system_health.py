from types import SimpleNamespace

from app import main, system


def test_disk_status_thresholds():
    assert system.disk_status(1.99) == "critical"
    assert system.disk_status(2.0) == "warning"
    assert system.disk_status(9.99) == "warning"
    assert system.disk_status(10.0) == "ok"


def test_disk_info_converts_usage_to_gb(monkeypatch, tmp_path):
    monkeypatch.setattr(
        system.shutil,
        "disk_usage",
        lambda path: SimpleNamespace(total=100 * system.GIB, used=37 * system.GIB, free=63 * system.GIB),
    )

    assert system.disk_info(tmp_path) == {
        "total_gb": 100.0,
        "used_gb": 37.0,
        "free_gb": 63.0,
        "used_percent": 37.0,
    }


def test_system_health_reports_disk_and_active_jobs(monkeypatch):
    monkeypatch.setattr(main.system, "disk_info", lambda path: {
        "total_gb": 100.0, "used_gb": 95.0, "free_gb": 5.0, "used_percent": 95.0,
    })
    monkeypatch.setattr(main.media, "FFMPEG", "/usr/bin/ffmpeg")
    monkeypatch.setattr(main.store, "jobs", {
        "running": {"status": "rendering"},
        "done": {"status": "done"},
        "failed": {"status": "error"},
    })
    monkeypatch.setattr(main, "tasks", set())

    result = main.get_system_health()

    assert result["status"] == "warning"
    assert result["disk"]["free_gb"] == 5.0
    assert result["ffmpeg_installed"] is True
    assert result["active_jobs"] == 1
    assert result["active_tasks"] == 0
    assert result["timestamp"].endswith("Z")
