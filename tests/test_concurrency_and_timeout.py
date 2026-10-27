import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from app import media, pipeline, security
from app.jobs import store


def test_concurrency_semaphore_limits_renders_and_sets_queued_status(tmp_path):
    async def _test():
        job_id = "test-job-conc"
        job_dir = tmp_path / "jobs" / job_id
        (job_dir / "clips").mkdir(parents=True, exist_ok=True)
        fake_source = job_dir / "source.mp4"
        fake_source.write_bytes(b"dummy video data")

        job = {
            "id": job_id,
            "name": "conc_test",
            "source": "source.mp4",
            "source_type": "upload",
            "options": {"aspect": "9:16", "layout": "crop", "subtitles": False, "remove_silence": False},
            "meta": {"width": 1080, "height": 1920, "duration": 60.0, "has_audio": False, "fps": 30.0},
            "status": "rendering",
            "stage": "Merender klip…",
            "progress": 0.0,
            "error": None,
            "clips": [],
            "logs": [],
        }
        store.jobs[job_id] = job

        clip1 = pipeline.new_clip(job, 0, 10, "Clip 1")
        clip2 = pipeline.new_clip(job, 10, 20, "Clip 2")

        render1_started = asyncio.Event()
        render1_can_finish = asyncio.Event()
        max_active_renders = 0
        active_renders = 0

        async def mock_render_clip(*args, **kwargs):
            nonlocal active_renders, max_active_renders
            active_renders += 1
            max_active_renders = max(max_active_renders, active_renders)
            render1_started.set()
            await render1_can_finish.wait()
            active_renders -= 1

        # Force semaphore limit to 1
        test_sem = asyncio.Semaphore(1)
        with patch.object(pipeline, "render_lock", test_sem), \
             patch("app.media.render_clip", side_effect=mock_render_clip), \
             patch.object(store, "dir", return_value=job_dir):

            t1 = asyncio.create_task(pipeline.render(job, clip1))
            t2 = asyncio.create_task(pipeline.render(job, clip2))

            # Wait until clip1 has started rendering and acquired semaphore
            await render1_started.wait()
            # Give event loop a cycle so clip2 attempts to acquire semaphore
            await asyncio.sleep(0.05)

            # Clip 1 is rendering
            assert clip1["status"] == "rendering"

            # Clip 2 MUST be waiting in queue with status "queued" and stage "Menunggu antrean..."
            assert clip2["status"] == "queued"
            assert clip2["stage"] == "Menunggu antrean..."

            # Now let clip1 complete
            render1_can_finish.set()
            await asyncio.gather(t1, t2)

            # Both clips should now be done/ready
            assert clip1["status"] == "ready"
            assert clip2["status"] == "ready"
            # Concurrency must not have exceeded 1
            assert max_active_renders == 1

        store.jobs.pop(job_id, None)

    asyncio.run(_test())


def test_run_ffmpeg_kills_process_on_timeout(monkeypatch):
    async def _test():
        monkeypatch.setattr(security, "execution_timeout_seconds", lambda: 0.2)

        # We call run_ffmpeg with args that would sleep for 10 seconds (using -re to throttle to real time)
        with pytest.raises(media.FFmpegTimeoutError) as exc_info:
            await media.run_ffmpeg(["-re", "-f", "lavfi", "-i", "nullsrc=s=128x128:d=10", "-f", "null", "-"],
                                   duration=10.0, timeout=0.2)

        assert "melebihi batas waktu" in str(exc_info.value)

    asyncio.run(_test())


def test_probe_times_out_and_raises():
    async def _test():
        fake_path = Path("/dev/zero")
        with pytest.raises(media.FFmpegTimeoutError):
            await media.probe(fake_path, timeout=0.1)

    asyncio.run(_test())


def test_pipeline_render_handles_timeout_gracefully(tmp_path):
    async def _test():
        job_id = "test-job-timeout"
        job_dir = tmp_path / "jobs" / job_id
        (job_dir / "clips").mkdir(parents=True, exist_ok=True)
        fake_source = job_dir / "source.mp4"
        fake_source.write_bytes(b"dummy video data")

        job = {
            "id": job_id,
            "name": "timeout_test",
            "source": "source.mp4",
            "source_type": "upload",
            "options": {"aspect": "9:16", "layout": "crop", "subtitles": False, "remove_silence": False},
            "meta": {"width": 1080, "height": 1920, "duration": 60.0, "has_audio": False, "fps": 30.0},
            "status": "rendering",
            "stage": "Merender klip…",
            "progress": 0.0,
            "error": None,
            "clips": [],
            "logs": [],
        }
        store.jobs[job_id] = job
        clip = pipeline.new_clip(job, 0, 10, "Hanging Clip")

        async def mock_render_hang(*args, **kwargs):
            await asyncio.sleep(10)

        with patch.object(security, "execution_timeout_seconds", return_value=0.2), \
             patch.object(security, "execution_timeout_minutes", return_value=1), \
             patch("app.media.render_clip", side_effect=mock_render_hang), \
             patch.object(store, "dir", return_value=job_dir):

            await pipeline.render(job, clip)

            # Clip status must be error and log must indicate timeout
            assert clip["status"] == "error"
            assert "melebihi batas waktu" in clip["error"]

        store.jobs.pop(job_id, None)

    asyncio.run(_test())
