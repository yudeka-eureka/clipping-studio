import pytest
from app import main


@pytest.fixture(autouse=True)
def clean_rate_limiter(monkeypatch):
    monkeypatch.setattr(main, "PUBLIC_MODE", False)
    main.job_rate_limiter.limit = main.JOB_RATE_LIMIT
    main.job_rate_limiter.clear()
    yield
    main.job_rate_limiter.limit = main.JOB_RATE_LIMIT
    main.job_rate_limiter.clear()
