from app import main
from app.jobs import Store


def test_public_job_removes_ai_context():
    job = {
        "id": "job-1",
        "options": {},
        "_ai_context": {"provider": "gemini", "key": "secret-key", "model": "model-x"},
    }

    public = Store.public_job(job)

    assert "_ai_context" not in public
    assert "secret-key" not in str(public)


def test_job_log_redacts_request_key():
    job = {"_ai_context": {"key": "secret-key"}}

    assert Store.redact(job, "provider rejected secret-key") == "provider rejected [REDACTED]"


def test_public_request_context_requires_key(monkeypatch):
    monkeypatch.setattr(main, "PUBLIC_MODE", True)

    context = main._request_ai_context("openai", "secret-key", "gpt-test")

    assert context == {"provider": "openai", "key": "secret-key", "model": "gpt-test"}
