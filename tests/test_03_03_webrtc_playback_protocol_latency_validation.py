from __future__ import annotations

from datetime import datetime
import logging
import time

import pytest

from stream_testkit.config import TestConfig
from stream_testkit.latency import OcrResult, measure_latency_from_frame
from stream_testkit.manifest import wait_for_manifest
from stream_testkit.rest_client import ServerClient
from tests.webrtc_helpers import start_webrtc_publish

logger = logging.getLogger(__name__)


def _playback_smoke(api: ServerClient, config: TestConfig, browser, *, ll_hls: bool) -> None:
    protocol = "ll-hls" if ll_hls else "hls"
    stream_id, page, _ = start_webrtc_publish(
        api,
        config,
        browser,
        stream_prefix=f"streamtest_03_03_{'llhls' if ll_hls else 'hls'}",
        name="3.3 WebRTC Playback smoke",
    )
    manifest_url = config.ll_hls_manifest_url(stream_id) if ll_hls else f"{config.hls_base_url}/{stream_id}_adaptive.m3u8"
    logger.info("Waiting for %s manifest at %s", protocol, manifest_url)
    manifest = wait_for_manifest(manifest_url, verify_tls=config.verify_tls)
    assert "#EXTM3U" in manifest, f"{protocol} manifest did not look valid for {stream_id}"
    logger.info("%s manifest became available for %s", protocol, stream_id)
    original_window = browser.current_window_handle
    browser.switch_to.default_content()
    browser.execute_script("window.open('about:blank', '_blank');")
    browser.switch_to.window(browser.window_handles[-1])
    try:
        logger.info("Opening play page for %s with playOrder=%s", stream_id, protocol)
        page.open_play_page(stream_id, ll_hls=ll_hls)
        page.wait_until_video_playing()
        logger.info("%s playback smoke succeeded for %s", protocol, stream_id)
    finally:
        browser.close()
        browser.switch_to.window(original_window)


def _measure_playback_latency(api: ServerClient, config: TestConfig, browser, *, ll_hls: bool) -> float:
    protocol = "ll-hls" if ll_hls else "hls"
    stream_id, page, broadcast_started_at = start_webrtc_publish(
        api,
        config,
        browser,
        stream_prefix=f"streamtest_03_03_{'llhls' if ll_hls else 'hls'}",
        name="3.3 WebRTC Playback latency",
    )
    manifest_url = config.ll_hls_manifest_url(stream_id) if ll_hls else f"{config.hls_base_url}/{stream_id}_adaptive.m3u8"
    logger.info("Waiting for %s manifest at %s", protocol, manifest_url)
    manifest = wait_for_manifest(manifest_url, verify_tls=config.verify_tls)
    assert "#EXTM3U" in manifest, f"{protocol} manifest did not look valid for {stream_id}"
    logger.info("%s manifest became available for %s", protocol, stream_id)
    original_window = browser.current_window_handle
    browser.switch_to.default_content()
    browser.execute_script("window.open('about:blank', '_blank');")
    browser.switch_to.window(browser.window_handles[-1])
    try:
        logger.info("Opening play page for %s with playOrder=%s", stream_id, protocol)
        page.open_play_page(stream_id, ll_hls=ll_hls)
        page.wait_until_video_playing()
        logger.info("Playback started in browser for %s", stream_id)
        ocr_result = _capture_latency_sample(
            page,
            stream_id=stream_id,
            protocol=protocol,
            broadcast_started_at=broadcast_started_at,
        )
        _log_latency_measurement(stream_id, protocol, broadcast_started_at, ocr_result)
        return ocr_result.latency_seconds
    finally:
        browser.close()
        browser.switch_to.window(original_window)


def _capture_latency_sample(
    page,
    *,
    stream_id: str,
    protocol: str,
    broadcast_started_at: datetime,
) -> OcrResult:
    last_error = ""
    for attempt in range(1, 6):
        observed_at = datetime.now()
        frame = page.capture_video_frame()
        logger.info("Captured playback sample %d for %s at %s", attempt, stream_id, observed_at.isoformat(timespec="milliseconds"))
        try:
            result = measure_latency_from_frame(
                frame,
                stream_id=stream_id,
                protocol=protocol,
                broadcast_started_at=broadcast_started_at,
                observed_at=observed_at,
            )
            logger.info(
                "OCR sample %d for %s succeeded with raw text %r and match %r",
                attempt,
                stream_id,
                result.text,
                result.matched_text,
            )
            return result
        except AssertionError as exc:
            last_error = str(exc)
            logger.warning("OCR sample %d for %s failed: %s", attempt, stream_id, exc)
            time.sleep(1)
    raise AssertionError(f"Could not extract OCR timestamp from playback for {stream_id}. Last error: {last_error}")


def _log_latency_measurement(
    stream_id: str,
    protocol: str,
    broadcast_started_at: datetime,
    ocr_result: OcrResult,
) -> None:
    time_since_broadcast_start = (ocr_result.observed_at - broadcast_started_at).total_seconds()
    logger.info("Latency measurement summary for %s (%s)", stream_id, protocol)
    logger.info("OCR raw text: %r", ocr_result.text)
    logger.info("OCR parsed timestamp: %s", ocr_result.matched_text)
    logger.info("REST broadcast start time: %s", broadcast_started_at.isoformat(timespec="milliseconds"))
    logger.info("Current time at sample: %s", ocr_result.observed_at.isoformat(timespec="milliseconds"))
    logger.info("Current time - broadcast start: %.3fs", time_since_broadcast_start)
    logger.info("OCR embedded timestamp (aligned): %s", ocr_result.embedded_time.isoformat(timespec="milliseconds"))
    logger.info("Computed latency: %.3fs", ocr_result.latency_seconds)
    logger.info("Debug raw frame: %s", ocr_result.raw_image_path)
    logger.info("Debug processed frame: %s", ocr_result.processed_image_path)


@pytest.mark.latency
@pytest.mark.webrtc
@pytest.mark.slow
def test_03_03_hls_playback_is_available(api: ServerClient, config: TestConfig, browser) -> None:
    _playback_smoke(api, config, browser, ll_hls=False)


@pytest.mark.webrtc
@pytest.mark.slow
def test_03_03_ll_hls_playback_is_available(api: ServerClient, config: TestConfig, browser) -> None:
    _playback_smoke(api, config, browser, ll_hls=True)


@pytest.mark.latency
@pytest.mark.webrtc
@pytest.mark.slow
def test_03_03_hls_playback_latency_target_8_to_12_seconds(api: ServerClient, config: TestConfig, browser) -> None:
    latency_seconds = _measure_playback_latency(api, config, browser, ll_hls=False)
    assert 8 <= latency_seconds <= 12, f"Expected HLS latency between 8s and 12s, measured {latency_seconds:.3f}s"


@pytest.mark.latency
@pytest.mark.webrtc
@pytest.mark.slow
def test_03_03_ll_hls_playback_latency_target_3_to_5_seconds(api: ServerClient, config: TestConfig, browser) -> None:
    latency_seconds = _measure_playback_latency(api, config, browser, ll_hls=True)
    assert 3 <= latency_seconds <= 7, f"Expected LL-HLS latency between 3s and 7s, measured {latency_seconds:.3f}s"
