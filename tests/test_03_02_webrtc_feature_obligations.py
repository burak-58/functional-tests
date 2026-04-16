from __future__ import annotations

import hashlib
import logging
import time
from urllib.parse import urlparse
import uuid

import pytest
import requests

from stream_testkit.config import TestConfig
from stream_testkit.rest_client import ServerClient
from tests.webrtc_helpers import start_webrtc_publish

logger = logging.getLogger(__name__)


def _wait_for_broadcast(api: ServerClient, stream_id: str, *, application: str, timeout_seconds: int = 60) -> dict[str, object]:
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        try:
            broadcast = api.get_broadcast(stream_id, application=application)
            if broadcast:
                return broadcast
        except requests.RequestException as exc:
            last_error = str(exc)
        except AssertionError as exc:
            last_error = str(exc)
        time.sleep(2)
    raise AssertionError(
        f"Broadcast {stream_id} was not available in application {application} before timeout. Last error: {last_error}"
    )


def _preview_signature(response: requests.Response) -> str:
    return hashlib.sha1(response.content).hexdigest()


def _preview_observation(response: requests.Response) -> dict[str, str | int]:
    return {
        "signature": _preview_signature(response),
        "last_modified": response.headers.get("Last-Modified", ""),
        "etag": response.headers.get("ETag", ""),
        "content_length": response.headers.get("Content-Length", str(len(response.content))),
    }


def _preview_changed(previous: dict[str, str | int], current: dict[str, str | int]) -> bool:
    return any(current[key] != previous[key] for key in ("signature", "last_modified", "etag", "content_length"))


def _recording_candidate_urls(config: TestConfig, stream_id: str) -> list[str]:
    return [
        f"{config.hls_base_url}/{stream_id}.mp4",
        f"{config.hls_base_url}/{stream_id}-muted.mp4",
        f"{config.hls_base_url}/{stream_id}_360p800kbps.mp4",
        f"{config.hls_base_url}/{stream_id}_540p1200kbps.mp4",
        f"{config.hls_base_url}/{stream_id}_720p2000kbps.mp4",
        f"{config.hls_base_url}/{stream_id}_1080p2500kbps.mp4",
        f"{config.hls_base_url}/{stream_id}-muted_360p800kbps.mp4",
        f"{config.hls_base_url}/{stream_id}-muted_540p1200kbps.mp4",
        f"{config.hls_base_url}/{stream_id}-muted_720p2000kbps.mp4",
    ]


@pytest.mark.webrtc
@pytest.mark.slow
def test_03_02_webrtc_push_endpoint_can_be_attached(api: ServerClient, config: TestConfig, browser) -> None:
    stream_id = f"streamtest_03_02_push_{uuid.uuid4().hex[:8]}"
    endpoint_stream_id = f"{stream_id}_rtmp_endpoint"
    server_host = urlparse(config.normalized_server_url).hostname
    assert server_host, f"Could not determine server host from {config.normalized_server_url}"
    endpoint_url = f"rtmp://{server_host}/LiveApp/{endpoint_stream_id}"
    logger.info("Creating broadcast for %s WebRTC RTMP push", stream_id)
    api.create_broadcast(stream_id, "3.2 WebRTC RTMP Push")
    response = api.add_rtmp_endpoint(stream_id, endpoint_url)
    assert response
    published_stream_id, _, _ = start_webrtc_publish(
        api,
        config,
        browser,
        stream_prefix=stream_id,
        name="3.2 WebRTC RTMP Push",
        stream_id=stream_id,
        create_broadcast=False,
    )
    source_broadcast = _wait_for_broadcast(api, published_stream_id, application=config.application)
    forwarded_broadcast = _wait_for_broadcast(api, endpoint_stream_id, application="LiveApp")
    assert source_broadcast, f"Source broadcast {published_stream_id} was not created in {config.application}"
    assert forwarded_broadcast, f"Forwarded broadcast {endpoint_stream_id} was not created in LiveApp"


@pytest.mark.webrtc
@pytest.mark.slow
@pytest.mark.panel_auth
def test_03_02_webrtc_png_snapshots_are_created(api: ServerClient, config: TestConfig, browser) -> None:
    settings = api.get_application_settings()
    preview_period_ms = int(settings.get("createPreviewPeriod", 0) or 5000)
    preview_period_seconds = max(preview_period_ms / 1000.0, 1.0)
    logger.info("Preview interval for %s is configured as %sms (%.3fs)", config.application, preview_period_ms, preview_period_seconds)
    stream_id, _, _ = start_webrtc_publish(
        api,
        config,
        browser,
        stream_prefix="streamtest_03_02_snapshot",
        name="3.2 WebRTC PNG Snapshot",
    )
    preview_url = f"{config.preview_base_url}/{stream_id}.png"
    first_preview_at: float | None = None
    first_observation: dict[str, str | int] | None = None
    initial_preview_at: float | None = None
    refresh_observations: list[tuple[float, dict[str, str | int]]] = []
    deadline = time.time() + max(30, config.duration_seconds, preview_period_seconds * 5 + 10)
    while time.time() < deadline:
        try:
            response = requests.get(preview_url, timeout=10, verify=config.verify_tls)
            if response.ok and response.headers.get("Content-Type", "").lower().startswith("image/") and response.content:
                now = time.time()
                observation = _preview_observation(response)
                if first_observation is None:
                    first_observation = observation
                    first_preview_at = now
                    initial_preview_at = now
                    logger.info("First preview detected for %s at %.3f from %s: %s", stream_id, now, preview_url, observation)
                elif (
                    first_preview_at is not None
                    and now - first_preview_at >= preview_period_seconds
                    and _preview_changed(first_observation, observation)
                ):
                    previous_at = first_preview_at if not refresh_observations else refresh_observations[-1][0]
                    refresh_observations.append((now, observation))
                    logger.info(
                        "Preview refresh %d detected for %s at %.3f after %.3fs from previous observation at %s: %s",
                        len(refresh_observations),
                        stream_id,
                        now,
                        now - previous_at,
                        preview_url,
                        observation,
                    )
                    if len(refresh_observations) >= 2:
                        break
                    first_observation = observation
                    first_preview_at = now
        except requests.RequestException:
            pass
        time.sleep(1)
    assert first_observation is not None and first_preview_at is not None and initial_preview_at is not None, (
        f"No preview PNG became available for {stream_id} at {preview_url}"
    )
    assert len(refresh_observations) >= 2, (
        f"Preview PNG became available for {stream_id} at {preview_url}, but it did not update within "
        f"{preview_period_seconds * 5 + 10:.1f}s enough times to verify cadence."
    )


@pytest.mark.webrtc
@pytest.mark.slow
def test_03_02_webrtc_recording_created_for_published_stream(api: ServerClient, config: TestConfig, browser) -> None:
    stream_id, page, _ = start_webrtc_publish(
        api,
        config,
        browser,
        stream_prefix="streamtest_03_02_recording",
        name="3.2 WebRTC Recording",
    )
    recording_urls = _recording_candidate_urls(config, stream_id)
    _wait_for_broadcast(api, stream_id, application=config.application)
    time.sleep(10)
    logger.info("Stopping WebRTC publishing for %s so recording can finalize", stream_id)
    page.stop_publishing()
    time.sleep(5)
    deadline = time.time() + 90
    observations: dict[str, str] = {}
    while time.time() < deadline:
        for recording_url in recording_urls:
            try:
                response = requests.get(recording_url, timeout=10, verify=config.verify_tls)
                if response.ok and response.headers.get("Content-Type", "").lower().startswith(("video/", "application/octet-stream")) and response.content:
                    logger.info("Recording became available for %s at %s", stream_id, recording_url)
                    return
                observations[recording_url] = (
                    f"HTTP {response.status_code}, content-type={response.headers.get('Content-Type')!r}, "
                    f"size={len(response.content)}"
                )
            except requests.RequestException as exc:
                observations[recording_url] = str(exc)
        time.sleep(2)
    raise AssertionError(
        f"No MP4 recording became available for {stream_id}. "
        f"Tried URLs: {observations}"
    )
