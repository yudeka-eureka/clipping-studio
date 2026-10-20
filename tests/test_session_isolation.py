import pytest
from fastapi import HTTPException

from app import main


def test_public_jobs_are_filtered_by_session(monkeypatch):
    monkeypatch.setattr(main, "PUBLIC_MODE", True)
    token = main.CURRENT_SESSION.set("11111111-1111-4111-8111-111111111111")
    try:
        monkeypatch.setattr(main.store, "jobs", {
            "owned": {
                "id": "owned", "created_at": 2, "owner_session_id": main.current_session_id(),
            },
            "other": {
                "id": "other", "created_at": 1,
                "owner_session_id": "22222222-2222-4222-8222-222222222222",
            },
        })

        assert [job["id"] for job in main.list_jobs()] == ["owned"]
        assert "owner_session_id" not in main.list_jobs()[0]
        assert main.get_job("owned")["id"] == "owned"
        with pytest.raises(HTTPException) as error:
            main.get_job("other")
        assert error.value.status_code == 404
    finally:
        main.CURRENT_SESSION.reset(token)
