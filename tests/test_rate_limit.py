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
