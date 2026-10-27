from unittest.mock import MagicMock
from app import main, gemini
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


def test_gemini_list_models_filters_unavailable_models(monkeypatch):
    class FakeModel:
        def __init__(self, name, supported_actions=None):
            self.name = name
            self.supported_actions = supported_actions or ["generateContent"]

    fake_client = MagicMock()
    fake_client.models.list.return_value = [
        FakeModel("models/gemini-2.5-flash"),
        FakeModel("models/gemini-2.5-flash-lite"),
        FakeModel("models/gemini-2.5-pro"),
        FakeModel("models/gemini-3.8-flash"),
        FakeModel("models/gemini-3.7-flash"),
        FakeModel("models/embedding-001", supported_actions=["embedContent"]),
    ]

    monkeypatch.setattr(gemini, "client", lambda key: fake_client)
    monkeypatch.setattr(gemini, "_is_model_available", lambda c, m: True)

    models = gemini.list_models("dummy-key")

    assert "gemini-3.8-flash" in models
    assert "gemini-3.7-flash" in models
    assert "gemini-2.5-flash" not in models
    assert "gemini-2.5-flash-lite" not in models
    assert "gemini-2.5-pro" not in models
    assert "embedding-001" not in models
