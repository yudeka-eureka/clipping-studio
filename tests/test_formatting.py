import pytest

from app.cli import hms
from app.media import _srt_time, _vtt_time, write_vtt


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


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0.0, "00:00:00.000"),
        (65.123, "00:01:05.123"),
        (3665.5, "01:01:05.500"),
        (-5.0, "00:00:00.000"),
        (59.9996, "00:01:00.000"),
    ],
)
def test_vtt_time_formats_seconds_and_clamps_negative(seconds, expected):
    assert _vtt_time(seconds) == expected


def test_write_vtt_w3c_compliance(tmp_path):
    captions = [
        {"start": 1.2, "end": 4.5, "text": "Teks subtitle di sini"},
        {"start": 5.0, "end": 8.25, "text": "Baris kedua subtitle"},
    ]
    out_file = tmp_path / "test.vtt"
    ok = write_vtt(captions, out_file)

    assert ok is True
    content = out_file.read_text(encoding="utf-8")
    assert content.startswith("WEBVTT\n\n")
    assert "1\n00:00:01.200 --> 00:00:04.500\nTeks subtitle di sini\n" in content
    assert "2\n00:00:05.000 --> 00:00:08.250\nBaris kedua subtitle\n" in content


def test_write_vtt_returns_false_on_empty(tmp_path):
    out_file = tmp_path / "empty.vtt"
    assert write_vtt([], out_file) is False
    assert not out_file.exists()

