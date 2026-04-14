from __future__ import annotations

from datetime import datetime
import logging
import time
import uuid

import pytest

from stream_testkit.config import TestConfig
from stream_testkit.latency import extract_broadcast_start_time
from stream_testkit.pages import StreamAppPage
from stream_testkit.rest_client import ServerClient

logger = logging.getLogger(__name__)


def require_webrtc_media(config: TestConfig) -> None:
    if not config.media_file:
        pytest.skip("--media-file is required for deterministic WebRTC ingest tests")


def wait_for_broadcast_start(api: ServerClient, stream_id: str, *, timeout_seconds: int = 60) -> datetime:
    deadline = time.time() + timeout_seconds
    last_broadcast: dict[str, object] | None = None
    while time.time() < deadline:
        broadcast = api.get_broadcast(stream_id)
        last_broadcast = broadcast
        broadcast_started_at = extract_broadcast_start_time(broadcast)
        logger.info(
            "Broadcast timing poll for %s: start=%s raw_fields=%s",
            stream_id,
            broadcast_started_at.isoformat(timespec="milliseconds") if broadcast_started_at else None,
            {key: broadcast.get(key) for key in ("status", "startTime", "absoluteStartTimeMs", "date")},
        )
        if broadcast_started_at is not None:
            return broadcast_started_at
        time.sleep(1)
    raise AssertionError(f"Broadcast start time was not available for {stream_id}. Last broadcast: {last_broadcast}")


def start_webrtc_publish(
    api: ServerClient,
    config: TestConfig,
    browser,
    *,
    stream_prefix: str,
    name: str,
    stream_id: str | None = None,
    create_broadcast: bool = True,
) -> tuple[str, StreamAppPage, datetime]:
    require_webrtc_media(config)
    stream_id = stream_id or f"{stream_prefix}_{uuid.uuid4().hex[:8]}"
    if create_broadcast:
        logger.info("Creating broadcast for %s", stream_id)
        api.create_broadcast(stream_id, name)
    page = StreamAppPage(browser, config)
    logger.info("Opening publish page for %s", stream_id)
    page.open_publish_page(stream_id)
    logger.info("Starting WebRTC publishing for %s", stream_id)
    page.start_publishing()
    page.wait_until_video_playing(in_publish_frame=True)
    logger.info("WebRTC local publish preview became active for %s", stream_id)
    broadcast_started_at = wait_for_broadcast_start(api, stream_id)
    logger.info(
        "Broadcast %s started at %s according to REST",
        stream_id,
        broadcast_started_at.isoformat(timespec="milliseconds"),
    )
    return stream_id, page, broadcast_started_at
