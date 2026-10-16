from app import pricing


def _entry(**overrides):
    entry = {
        "t": 1_700_000_000,
        "model": "test-model",
        "prompt_tokens": 1_000,
        "audio_tokens": 0,
        "cached_tokens": 0,
        "output_tokens": 300,
        "thoughts_tokens": 0,
    }
    entry.update(overrides)
    return entry


def test_cost_is_zero_on_free_tier(monkeypatch):
    monkeypatch.setattr(pricing, "settings", lambda: {"tier": "free", "overrides": {}})

    result = pricing.cost(_entry(model="gemini-3.8-flash"))

    assert result == {"usd": 0.0, "tier": "free", "price": None}


def test_cost_uses_paid_input_and_output_rates(monkeypatch):
    monkeypatch.setattr(
        pricing,
        "settings",
        lambda: {
            "tier": "paid",
            "overrides": {
                "test-model": {"input": 2.0, "audio": 4.0, "output": 8.0},
            },
        },
    )

    result = pricing.cost(
        _entry(prompt_tokens=1_000, output_tokens=300, thoughts_tokens=50)
    )

    assert result["tier"] == "paid"
    assert result["usd"] == 0.0048
    assert result["price"]["source"] == "manual"


def test_cost_separates_audio_and_cached_tokens(monkeypatch):
    monkeypatch.setattr(
        pricing,
        "settings",
        lambda: {
            "tier": "paid",
            "overrides": {
                "test-model": {"input": 2.0, "audio": 4.0, "output": 8.0},
            },
        },
    )

    result = pricing.cost(
        _entry(prompt_tokens=1_000, audio_tokens=100, cached_tokens=200, output_tokens=300)
    )

    assert result["usd"] == 0.0046


def test_price_for_matches_model_preview_suffix(monkeypatch):
    monkeypatch.setattr(pricing, "settings", lambda: {"tier": "paid", "overrides": {}})

    result = pricing.price_for("gemini-3.8-flash-preview-09-2026")

    assert result["input"] == 0.75
    assert result["output"] == 3.75
    assert result["source"] == "default"


def test_price_for_returns_long_prompt_rate(monkeypatch):
    monkeypatch.setattr(pricing, "settings", lambda: {"tier": "paid", "overrides": {}})

    result = pricing.price_for("gemini-2.5-pro", prompt_tokens=pricing.LONG_PROMPT + 1)

    assert result["input"] == 2.5
    assert result["output"] == 15.0


def test_price_for_unknown_model_returns_none(monkeypatch):
    monkeypatch.setattr(pricing, "settings", lambda: {"tier": "paid", "overrides": {}})

    assert pricing.price_for("unknown-model") is None


def test_estimate_free_tier_has_zero_cost(monkeypatch):
    monkeypatch.setattr(pricing, "settings", lambda: {"tier": "free", "overrides": {}})

    result = pricing.estimate(
        duration=60, model="gemini-3.8-flash", num_clips=2, max_len=30,
        subtitles=True,
    )

    assert result["prompt_tokens"] == 18_600
    assert result["output_tokens"] == 2_240
    assert result["usd"] == 0.0
    assert result["tier"] == "free"
