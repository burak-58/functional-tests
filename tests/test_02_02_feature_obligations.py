from __future__ import annotations

import hashlib
import logging
import time
import uuid
from urllib.parse import urlparse

import pytest
import requests

from stream_testkit.config import TestConfig
from stream_testkit.ffmpeg import start_rtmp_ingest, stop_process
from stream_testkit.rest_client import ServerClient

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


@pytest.mark.rtmp
@pytest.mark.slow
def test_02_02_rtmp_push_endpoint_can_be_attached(api: ServerClient, config: TestConfig) -> None:
    if not config.media_file:
        pytest.skip("--media-file is required for RTMP push verification")
    stream_id = f"streamtest_02_02_push_{uuid.uuid4().hex[:8]}"
    endpoint_stream_id = f"{stream_id}_rtmp_endpoint"
    server_host = urlparse(config.normalized_server_url).hostname
    assert server_host, f"Could not determine server host from {config.normalized_server_url}"
    endpoint_url = f"rtmp://{server_host}/LiveApp/{endpoint_stream_id}"
    api.create_broadcast(stream_id, "2.2 RTMP Push")
    response = api.add_rtmp_endpoint(stream_id, endpoint_url)
    assert response

    process = start_rtmp_ingest(
        config.media_file,
        f"{config.rtmp_base_url}/{stream_id}",
        video_bitrate="6000k",
        resolution="1920:1080",
        fps=30,
    )
    try:
        source_broadcast = _wait_for_broadcast(api, stream_id, application=config.application)
        forwarded_broadcast = _wait_for_broadcast(api, endpoint_stream_id, application="LiveApp")
    finally:
        stop_process(process)

    assert source_broadcast, f"Source broadcast {stream_id} was not created in {config.application}"
    assert forwarded_broadcast, f"Forwarded broadcast {endpoint_stream_id} was not created in LiveApp"


@pytest.mark.rtmp
@pytest.mark.slow
@pytest.mark.panel_auth
def test_02_02_png_snapshots_are_created(api: ServerClient, config: TestConfig) -> None:
    if not config.media_file:
        pytest.skip("--media-file is required for PNG snapshot verification")
    settings = api.get_application_settings()
    preview_period_ms = int(settings.get("createPreviewPeriod", 0) or 5000)
    preview_period_seconds = max(preview_period_ms / 1000.0, 1.0)
    logger.info("Preview interval for %s is configured as %sms (%.3fs)", config.application, preview_period_ms, preview_period_seconds)
    stream_id = f"streamtest_02_02_snapshot_{uuid.uuid4().hex[:8]}"
    api.create_broadcast(stream_id, "2.2 PNG Snapshot")
    preview_url = f"{config.preview_base_url}/{stream_id}.png"
    process = start_rtmp_ingest(
        config.media_file,
        f"{config.rtmp_base_url}/{stream_id}",
        video_bitrate="6000k",
        resolution="1920:1080",
        fps=30,
    )
    first_preview_at: float | None = None
    first_observation: dict[str, str | int] | None = None
    initial_preview_at: float | None = None
    refresh_observations: list[tuple[float, dict[str, str | int]]] = []
    try:
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
                        logger.info(
                            "First preview detected for %s at %.3f from %s: %s",
                            stream_id,
                            first_preview_at,
                            preview_url,
                            first_observation,
                        )
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
    finally:
        stop_process(process)
    assert first_observation is not None and first_preview_at is not None and initial_preview_at is not None, (
        f"No preview PNG became available for {stream_id} at {preview_url}"
    )
    assert len(refresh_observations) >= 2, (
        f"Preview PNG became available for {stream_id} at {preview_url}, but it did not update within "
        f"{preview_period_seconds * 5 + 10:.1f}s enough times to verify cadence. "
        f"Expected repeated updates about every {preview_period_seconds:.1f}s."
    )
    first_refresh_elapsed = refresh_observations[0][0] - initial_preview_at
    second_refresh_elapsed = refresh_observations[1][0] - refresh_observations[0][0]
    assert first_refresh_elapsed >= preview_period_seconds, (
        f"First preview refresh happened too quickly for {stream_id}. Expected at least {preview_period_seconds:.1f}s, "
        f"but saw {first_refresh_elapsed:.1f}s."
    )
    assert first_refresh_elapsed <= preview_period_seconds * 2.5 + 5, (
        f"First preview refresh happened too slowly for {stream_id}. Expected roughly {preview_period_seconds:.1f}s cadence, "
        f"but saw {first_refresh_elapsed:.1f}s."
    )
    assert second_refresh_elapsed >= preview_period_seconds, (
        f"Second preview refresh happened too quickly for {stream_id}. Expected at least {preview_period_seconds:.1f}s, "
        f"but saw {second_refresh_elapsed:.1f}s."
    )
    assert second_refresh_elapsed <= preview_period_seconds * 2.5 + 5, (
        f"Second preview refresh happened too slowly for {stream_id}. Expected roughly {preview_period_seconds:.1f}s cadence, "
        f"but saw {second_refresh_elapsed:.1f}s."
    )


@pytest.mark.rtmp
@pytest.mark.slow
def test_02_02_recording_created_for_ingested_stream(api: ServerClient, config: TestConfig) -> None:
    if not config.media_file:
        pytest.skip("--media-file is required for recording verification")
    stream_id = f"streamtest_02_02_recording_{uuid.uuid4().hex[:8]}"
    api.create_broadcast(stream_id, "2.2 Recording")
    recording_urls = [
        f"{config.hls_base_url}/{stream_id}.mp4",
        f"{config.hls_base_url}/{stream_id}-muted.mp4",
    ]
    process = start_rtmp_ingest(config.media_file, f"{config.rtmp_base_url}/{stream_id}", video_bitrate="6000k", resolution="1920:1080", fps=30)
    try:
        _wait_for_broadcast(api, stream_id, application=config.application)
        time.sleep(10)
    finally:
        stop_process(process)
    for recording_url in recording_urls:
        deadline = time.time() + 60
        last_error = ""
        while time.time() < deadline:
            try:
                response = requests.get(recording_url, timeout=10, verify=config.verify_tls)
                if response.ok and response.headers.get("Content-Type", "").lower().startswith(("video/", "application/octet-stream")) and response.content:
                    break
                last_error = (
                    f"HTTP {response.status_code}, content-type={response.headers.get('Content-Type')!r}, "
                    f"size={len(response.content)}"
                )
            except requests.RequestException as exc:
                last_error = str(exc)
            time.sleep(2)
        else:
            raise AssertionError(f"No MP4 recording became available for {stream_id} at {recording_url}. Last error: {last_error}")
