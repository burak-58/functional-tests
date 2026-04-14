from __future__ import annotations

from datetime import datetime

from stream_testkit.latency import _timestamp_to_timedelta, extract_broadcast_start_time


def test_extract_broadcast_start_time_prefers_epoch_ms_fields() -> None:
    broadcast = {
        "startTime": 1712918400123,
        "absoluteStartTimeMs": 1712918400456,
    }

    start_time = extract_broadcast_start_time(broadcast)

    assert start_time is not None
    assert start_time == datetime.fromtimestamp(1712918400456 / 1000.0)


def test_extract_broadcast_start_time_returns_none_without_usable_fields() -> None:
    assert extract_broadcast_start_time({"startTime": 0, "date": ""}) is None


def test_timestamp_to_timedelta_supports_single_digit_ocr_components() -> None:
    elapsed = _timestamp_to_timedelta({"hour": "0", "minute": "0", "second": "8", "millis": "5"})

    assert elapsed.total_seconds() == 8.5


def test_timestamp_to_timedelta_rejects_invalid_ocr_components() -> None:
    try:
        _timestamp_to_timedelta({"hour": "74", "minute": "45", "second": "20", "millis": "75"})
    except AssertionError as exc:
        assert "invalid hour" in str(exc)
    else:
        raise AssertionError("Expected invalid OCR timestamp to be rejected")
