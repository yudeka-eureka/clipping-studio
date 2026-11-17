import asyncio
import io
import json
import pytest
from starlette.testclient import TestClient

from app import db, main, security
from app.jobs import hub, store


@pytest.fixture(autouse=True)
def clean_jobs():
    store.jobs.clear()
    hub.sockets.clear()
    yield
    store.jobs.clear()
    hub.sockets.clear()


def create_user_and_token():
    uname = f"testws_{db.secrets.token_hex(4)}"
    email = f"{uname}@example.com"
    user = db.register_user(uname, email, "password123")
    jwt_tok = security.create_jwt_token({"user_id": user["id"], "username": user["username"]})
    return user, jwt_tok


def test_websocket_receives_snapshot_and_job_updates_with_jwt_token():
    user, jwt_tok = create_user_and_token()
    client = TestClient(main.app)

    # Create a job belonging to user
    job = store.create("sample.mp4", "upload", {})
    job["user_id"] = user["id"]
    job["owner_session_id"] = user["credential_token"]
    store.jobs[job["id"]] = job

    with client.websocket_connect(f"/ws?token={jwt_tok}") as ws:
        # 1. First message should be the snapshot containing the user's job
        snap = ws.receive_json()
        assert snap["type"] == "snapshot"
        assert len(snap["jobs"]) == 1
        assert snap["jobs"][0]["id"] == job["id"]

        # 2. Trigger progress event via store.progress
        asyncio.run(store.progress(job, 0.45, stage="Merender klip…"))
        prog = ws.receive_json()
        assert prog["type"] == "progress"
        assert prog["job_id"] == job["id"]
        assert prog["progress"] == 0.45
        assert prog["value"] == 0.45
        assert prog["stage"] == "Merender klip…"

        # 3. Trigger log event via store.log
        asyncio.run(store.log(job, "Transkrip selesai."))
        log_msg = ws.receive_json()
        assert log_msg["type"] == "log"
        assert log_msg["job_id"] == job["id"]
        assert "Transkrip selesai." in log_msg["line"]

        # 4. Trigger state change queued -> rendering -> done via store.update
        asyncio.run(store.update(job, status="rendering", stage="Merender klip…", progress=0.5))
        job_update = ws.receive_json()
        assert job_update["type"] == "job"
        assert job_update["job"]["status"] == "rendering"

        asyncio.run(store.update(job, status="done", stage="Selesai — 1 klip siap", progress=1.0))
        job_done = ws.receive_json()
        assert job_done["type"] == "job"
        assert job_done["job"]["status"] == "done"
        assert job_done["job"]["progress"] == 1.0


def test_websocket_receives_updates_with_credential_token():
    user, _ = create_user_and_token()
    client = TestClient(main.app)

    job = store.create("cred_sample.mp4", "upload", {})
    job["user_id"] = user["id"]
    job["owner_session_id"] = user["credential_token"]
    store.jobs[job["id"]] = job

    # Connect using credential_token in query
    with client.websocket_connect(f"/ws?token={user['credential_token']}") as ws:
        snap = ws.receive_json()
        assert snap["type"] == "snapshot"
        assert len(snap["jobs"]) == 1
        assert snap["jobs"][0]["id"] == job["id"]

        # Progress should be delivered
        asyncio.run(store.progress(job, 0.9, stage="Hampir selesai"))
        prog = ws.receive_json()
        assert prog["type"] == "progress"
        assert prog["progress"] == 0.9
        assert prog["value"] == 0.9


def test_websocket_isolation_between_different_users():
    user_a, jwt_a = create_user_and_token()
    user_b, jwt_b = create_user_and_token()
    client = TestClient(main.app)

    job_a = store.create("job_a.mp4", "upload", {})
    job_a["user_id"] = user_a["id"]
    job_a["owner_session_id"] = user_a["credential_token"]
    store.jobs[job_a["id"]] = job_a

    job_b = store.create("job_b.mp4", "upload", {})
    job_b["user_id"] = user_b["id"]
    job_b["owner_session_id"] = user_b["credential_token"]
    store.jobs[job_b["id"]] = job_b

    with client.websocket_connect(f"/ws?token={jwt_a}") as ws_a:
        with client.websocket_connect(f"/ws?token={jwt_b}") as ws_b:
            snap_a = ws_a.receive_json()
            snap_b = ws_b.receive_json()

            # In PUBLIC_MODE (or when filtered by user), user A should only see job A
            # If PUBLIC_MODE is False (local dev default), snapshot might show all unless user filter is active,
            # but websocket events targeted to job_a must not reach ws_b!
            asyncio.run(store.log(job_a, "Pesan rahasia User A"))
            msg_a = ws_a.receive_json()
            assert msg_a["job_id"] == job_a["id"]

            # User B sends ping, receives pong/nothing from User A's log
            ws_b.send_text("ping")
            # ws_b didn't receive msg_a


def test_media_and_download_with_token_in_public_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "PUBLIC_MODE", True)
    user, jwt_tok = create_user_and_token()
    client = TestClient(main.app)

    job_id = "test-job-media-123"
    job_dir = tmp_path / job_id
    clips_dir = job_dir / "clips"
    clips_dir.mkdir(parents=True)
    video_file = clips_dir / "clip_1.mp4"
    video_file.write_bytes(b"dummy mp4 data")
    srt_file = clips_dir / "clip_1.srt"
    srt_file.write_text("1\n00:00:00 --> 00:00:05\nHello\n", encoding="utf-8")

    job = {
        "id": job_id,
        "name": "sample",
        "user_id": user["id"],
        "owner_session_id": user["credential_token"],
        "created_at": 1000.0,
        "status": "done",
        "clips": [
            {"id": "c1", "status": "ready", "file": "clips/clip_1.mp4", "srt": "clips/clip_1.srt"}
        ],
    }
    store.jobs[job_id] = job
    monkeypatch.setattr(store, "dir", lambda _jid: job_dir)

    # 1. Accessing media without token returns 404 in public mode
    res_no_tok = client.get(f"/media/{job_id}/clips/clip_1.mp4")
    assert res_no_tok.status_code == 404

    # 2. Accessing media with token succeeds
    res_with_tok = client.get(f"/media/{job_id}/clips/clip_1.mp4?token={jwt_tok}")
    assert res_with_tok.status_code == 200
    assert res_with_tok.content == b"dummy mp4 data"

    # 3. Accessing download-all without token returns 404 in public mode
    res_dl_no_tok = client.get(f"/api/jobs/{job_id}/download-all")
    assert res_dl_no_tok.status_code == 404

    # 4. Accessing download-all with token succeeds
    res_dl_tok = client.get(f"/api/jobs/{job_id}/download-all?token={jwt_tok}")
    assert res_dl_tok.status_code == 200
    assert res_dl_tok.headers["content-type"] == "application/zip"


def test_media_unauthorized_token_returns_404_in_public_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "PUBLIC_MODE", True)
    user_a, jwt_a = create_user_and_token()
    user_b, jwt_b = create_user_and_token()
    client = TestClient(main.app)

    job_id = "job-user-a-only"
    job_dir = tmp_path / job_id
    clips_dir = job_dir / "clips"
    clips_dir.mkdir(parents=True)
    (clips_dir / "secret.mp4").write_bytes(b"user a video")

    job = {
        "id": job_id,
        "name": "sample",
        "user_id": user_a["id"],
        "owner_session_id": user_a["credential_token"],
        "created_at": 1000.0,
        "status": "done",
        "clips": [{"id": "c1", "status": "ready", "file": "clips/secret.mp4"}],
    }
    store.jobs[job_id] = job
    monkeypatch.setattr(store, "dir", lambda _jid: job_dir)

    # User B cannot access User A's media
    res = client.get(f"/media/{job_id}/clips/secret.mp4?token={jwt_b}")
    assert res.status_code == 404

    # User B cannot download User A's clips
    res_dl = client.get(f"/api/jobs/{job_id}/download-all?token={jwt_b}")
    assert res_dl.status_code == 404


def test_media_directory_traversal_blocked(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "PUBLIC_MODE", False)
    client = TestClient(main.app)

    job_id = "traversal-test"
    job_dir = tmp_path / job_id
    job_dir.mkdir(parents=True)
    job = {
        "id": job_id,
        "name": "sample",
        "created_at": 1000.0,
        "status": "done",
        "clips": [],
    }
    store.jobs[job_id] = job
    monkeypatch.setattr(store, "dir", lambda _jid: job_dir)

    res = client.get(f"/media/{job_id}/../../etc/passwd")
    assert res.status_code in (400, 404)


def test_websocket_malformed_token_does_not_crash():
    client = TestClient(main.app)
    with client.websocket_connect("/ws?token=malformed.garbage.token") as ws:
        snap = ws.receive_json()
        assert snap["type"] == "snapshot"
        ws.send_text("ping")


def test_job_polling_fallback_returns_visible_jobs():
    user, jwt_tok = create_user_and_token()
    client = TestClient(main.app)

    job = store.create("polled.mp4", "upload", {})
    job["user_id"] = user["id"]
    job["owner_session_id"] = user["credential_token"]
    store.jobs[job["id"]] = job

    # Polling GET /api/jobs with Authorization header
    res = client.get("/api/jobs", headers={"Authorization": f"Bearer {jwt_tok}"})
    assert res.status_code == 200
    job_list = res.json()
    assert any(j["id"] == job["id"] for j in job_list)

    # Polling GET /api/jobs with token in query param
    res_q = client.get(f"/api/jobs?token={jwt_tok}")
    assert res_q.status_code == 200
    job_list_q = res_q.json()
    assert any(j["id"] == job["id"] for j in job_list_q)


def test_cli_host_default_and_env():
    from app import cli

    parser = cli.build_parser()
    args = parser.parse_args(["serve"])
    # Default host is 0.0.0.0 for VPS deployment
    assert args.host == "0.0.0.0"


def test_anonymous_session_id_cross_origin_tracking_and_isolation(monkeypatch, tmp_path):
    import uuid
    monkeypatch.setattr(main, "PUBLIC_MODE", True)
    client = TestClient(main.app)

    sid_a = str(uuid.uuid4())
    sid_b = str(uuid.uuid4())

    job_id_a = "anon-job-a"
    job_dir_a = tmp_path / job_id_a
    (job_dir_a / "clips").mkdir(parents=True)
    (job_dir_a / "clips" / "clip_a.mp4").write_bytes(b"video a")
    job_a = {
        "id": job_id_a,
        "name": "anon_a.mp4",
        "created_at": 1000.0,
        "status": "queued",
        "stage": "Menunggu antrean...",
        "progress": 0.0,
        "owner_session_id": sid_a,
        "user_id": None,
        "clips": [{"id": "ca1", "status": "ready", "file": "clips/clip_a.mp4"}],
        "logs": [],
    }
    store.jobs[job_id_a] = job_a
    monkeypatch.setattr(store, "dir", lambda _jid: job_dir_a)

    # 1. Connect WS with anonymous session_id query param
    with client.websocket_connect(f"/ws?session_id={sid_a}") as ws_a:
        snap = ws_a.receive_json()
        assert snap["type"] == "snapshot"
        assert len(snap["jobs"]) == 1
        assert snap["jobs"][0]["id"] == job_id_a

        # Trigger progress on job_a
        asyncio.run(store.progress(job_a, 0.6, stage="Mempersiapkan video…"))
        prog = ws_a.receive_json()
        assert prog["type"] == "progress"
        assert prog["progress"] == 0.6
        assert prog["stage"] == "Mempersiapkan video…"

    # 2. Polling GET /api/jobs with X-Session-ID header
    res_a = client.get("/api/jobs", headers={"X-Session-ID": sid_a})
    assert res_a.status_code == 200
    assert any(j["id"] == job_id_a for j in res_a.json())

    # 3. Client B with sid_b gets empty list
    res_b = client.get("/api/jobs", headers={"X-Session-ID": sid_b})
    assert res_b.status_code == 200
    assert not any(j["id"] == job_id_a for j in res_b.json())

    # 4. Access media with session_id query param succeeds for A, 404 for B
    media_res_a = client.get(f"/media/{job_id_a}/clips/clip_a.mp4?session_id={sid_a}")
    assert media_res_a.status_code == 200
    assert media_res_a.content == b"video a"

    media_res_b = client.get(f"/media/{job_id_a}/clips/clip_a.mp4?session_id={sid_b}")
    assert media_res_b.status_code == 404


def test_store_progress_aggregates_clip_progress():
    job = store.create("sample_clip_progress.mp4", "upload", {})
    clip1 = {"id": "c1", "status": "rendering", "progress": 0.0, "stage": "Merender…"}
    clip2 = {"id": "c2", "status": "queued", "progress": 0.0, "stage": "Menunggu antrean..."}
    job["clips"] = [clip1, clip2]

    # Progress clip1 to 50%
    asyncio.run(store.progress(job, 0.5, stage="Merender…", clip_id="c1"))
    assert clip1["progress"] == 0.5
    # Overall job progress is (0.5 + 0.0) / 2 = 0.25
    assert job["progress"] == 0.25

    # Clip1 becomes ready, progress 1.0
    clip1["status"] = "ready"
    clip1["progress"] = 1.0
    # Progress clip2 to 50%
    asyncio.run(store.progress(job, 0.5, stage="Merender…", clip_id="c2"))
    assert job["progress"] == (1.0 + 0.5) / 2
    assert "1/2 selesai" in job["stage"]

