from __future__ import annotations

import logging

import pytest
import requests

from stream_testkit.manifest import fetch_manifest, is_media_playlist, variant_heights


def test_media_playlist_is_not_treated_as_variant_master() -> None:
    manifest = """#EXTM3U
#EXT-X-VERSION:3
#EXTINF:4.432000,
stream000000000.ts
"""

    assert is_media_playlist(manifest)
    assert variant_heights(manifest) == set()


def test_master_playlist_variant_heights_are_parsed() -> None:
    manifest = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360
stream_360p.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=1400000,RESOLUTION=960x540
stream_540p.m3u8
"""

    assert not is_media_playlist(manifest)
    assert variant_heights(manifest) == {360, 540}


def test_fetch_manifest_logs_url_and_success_result(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    class Response:
        status_code = 200
        text = "#EXTM3U"

        def raise_for_status(self) -> None:
            return None

    def fake_get(url: str, *, timeout: int, verify: bool) -> Response:
        assert url == "https://example.test/manifest.m3u8"
        assert timeout == 30
        assert verify is False
        return Response()

    monkeypatch.setattr(requests, "get", fake_get)

    with caplog.at_level(logging.INFO):
        manifest = fetch_manifest("https://example.test/manifest.m3u8")

    assert manifest == "#EXTM3U"
    assert "Manifest query https://example.test/manifest.m3u8" in caplog.text
    assert "Manifest query https://example.test/manifest.m3u8 -> HTTP 200" in caplog.text


def test_fetch_manifest_logs_url_and_failure_result(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    class Response:
        status_code = 404
        text = "missing manifest"

        def raise_for_status(self) -> None:
            raise requests.HTTPError("404 Client Error", response=self)

    def fake_get(url: str, *, timeout: int, verify: bool) -> Response:
        assert url == "https://example.test/missing.m3u8"
        assert timeout == 30
        assert verify is False
        return Response()

    monkeypatch.setattr(requests, "get", fake_get)

    with caplog.at_level(logging.WARNING):
        with pytest.raises(requests.HTTPError):
            fetch_manifest("https://example.test/missing.m3u8")

    assert "Manifest query https://example.test/missing.m3u8" in caplog.text
    assert "Manifest query https://example.test/missing.m3u8 -> HTTP 404: missing manifest" in caplog.text
