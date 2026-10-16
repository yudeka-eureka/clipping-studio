import pytest

from app.cli import hms
from app.media import _srt_time


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0.0, "00:00:00,000"),
        (65.123, "00:01:05,123"),
        (3665.5, "01:01:05,500"),
        (-5.0, "00:00:00,000"),
        (59.9996, "00:01:00,000"),
    ],
)
def test_srt_time_formats_seconds_and_clamps_negative(seconds, expected):
    assert _srt_time(seconds) == expected


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "00:00.0"),
        (95.4, "01:35.4"),
        (3600.0, "60:00.0"),
    ],
)
def test_hms_formats_minutes_and_seconds(seconds, expected):
    assert hms(seconds) == expected
