from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app, job_rate_limiter
from app.ratelimit import JobRateLimiter


def test_job_rate_limiter_allows_limit_then_blocks():
    limiter = JobRateLimiter(limit=2, window_seconds=60)

    assert limiter.allow("session-a", now=100) == (True, 0)
    assert limiter.allow("session-a", now=101) == (True, 0)
    allowed, retry_after = limiter.allow("session-a", now=102)
    assert allowed is False
    assert retry_after == 58


def test_job_rate_limiter_isolated_by_key_and_expires_events():
    limiter = JobRateLimiter(limit=1, window_seconds=60)

    assert limiter.allow("session-a", now=100)[0] is True
    assert limiter.allow("session-b", now=100)[0] is True
    assert limiter.allow("session-a", now=161)[0] is True


def test_job_rate_limiter_multi_key_atomic():
    limiter = JobRateLimiter(limit=1, window_seconds=60)

    # First request with ip1 and sess1 is allowed
    assert limiter.allow("ip:1.1.1.1", "sess:s1", now=100) == (True, 0)

    # Request from same IP but different session should be blocked
    allowed, retry_after = limiter.allow("ip:1.1.1.1", "sess:s2", now=105)
    assert allowed is False
    assert retry_after == 55

    # Request with different IP but same session should be blocked
    allowed, retry_after = limiter.allow("ip:2.2.2.2", "sess:s1", now=105)
    assert allowed is False

    # Request with different IP and different session is allowed
    assert limiter.allow("ip:2.2.2.2", "sess:s2", now=105) == (True, 0)


def test_api_jobs_rate_limiting_returns_429(monkeypatch):
    monkeypatch.setattr("app.main.JOB_RATE_LIMIT", 3)
    monkeypatch.setattr(job_rate_limiter, "limit", 3)
    job_rate_limiter.clear()

    client = TestClient(app)
    headers = {"X-Forwarded-For": "198.51.100.10"}

    # 3 job requests within limit
    for _ in range(3):
        res = client.post("/api/jobs", data={"url": "https://youtube.com/watch?v=valid123456"}, headers=headers)
        # Even if prepare_source or URL validation fails or succeeds, rate limit check happens first
        assert res.status_code != 429

    # 4th request must be rejected with 429 Too Many Requests
    res4 = client.post("/api/jobs", data={"url": "https://youtube.com/watch?v=valid123456"}, headers=headers)
    assert res4.status_code == 429
    assert "Batas pembuatan proyek tercapai" in res4.json()["detail"]
    assert "Retry-After" in res4.headers
    assert int(res4.headers["Retry-After"]) > 0


def test_api_jobs_rate_limiting_blocks_bots_without_cookies(monkeypatch):
    monkeypatch.setattr("app.main.JOB_RATE_LIMIT", 2)
    monkeypatch.setattr(job_rate_limiter, "limit", 2)
    job_rate_limiter.clear()

    client = TestClient(app)
    bot_headers = {"X-Forwarded-For": "203.0.113.50"}

    # Attacker does not send cookies
    res1 = client.post("/api/jobs", data={"url": "https://youtube.com/watch?v=test0000001"}, headers=bot_headers)
    assert res1.status_code != 429
    res2 = client.post("/api/jobs", data={"url": "https://youtube.com/watch?v=test0000002"}, headers=bot_headers)
    assert res2.status_code != 429

    # 3rd request from same bot IP
    res3 = client.post("/api/jobs", data={"url": "https://youtube.com/watch?v=test0000003"}, headers=bot_headers)
    assert res3.status_code == 429
    assert "Retry-After" in res3.headers


def test_api_jobs_rate_limiting_isolated_between_ips(monkeypatch):
    monkeypatch.setattr("app.main.JOB_RATE_LIMIT", 1)
    monkeypatch.setattr(job_rate_limiter, "limit", 1)
    job_rate_limiter.clear()

    client = TestClient(app)

    # IP 1 uses its quota
    res1 = client.post("/api/jobs", data={"url": "https://youtube.com/watch?v=test0000001"},
                       headers={"X-Forwarded-For": "10.0.0.1"})
    assert res1.status_code != 429

    # IP 1 is blocked
    res1_blocked = client.post("/api/jobs", data={"url": "https://youtube.com/watch?v=test0000001"},
                               headers={"X-Forwarded-For": "10.0.0.1"})
    assert res1_blocked.status_code == 429

    # IP 2 is still allowed
    res2 = client.post("/api/jobs", data={"url": "https://youtube.com/watch?v=test0000002"},
                       headers={"X-Forwarded-For": "10.0.0.2"})
    assert res2.status_code != 429
