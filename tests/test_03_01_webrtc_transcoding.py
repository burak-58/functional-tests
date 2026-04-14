from __future__ import annotations

import logging
from urllib.parse import urljoin

import pytest

from stream_testkit.config import TestConfig
from stream_testkit.ffmpeg import audio_streams, ffprobe, video_streams, wait_for_stream_probe
from stream_testkit.manifest import is_media_playlist, manifest_summary, parse_variants, variant_heights, wait_for_manifest
from stream_testkit.rest_client import ServerClient
from tests.webrtc_helpers import start_webrtc_publish

logger = logging.getLogger(__name__)


@pytest.mark.webrtc
@pytest.mark.slow
def test_03_01_webrtc_ingest_does_not_generate_variant_above_source_height(
    api: ServerClient, config: TestConfig, browser
) -> None:
    assert config.media_file is not None
    source_probe = ffprobe(str(config.media_file))
    source_videos = video_streams(source_probe)
    assert source_videos, f"Configured media file has no video stream: {config.media_file}"
    source_height = int(source_videos[0]["height"])
    stream_id, _, _ = start_webrtc_publish(
        api,
        config,
        browser,
        stream_prefix="streamtest_03_01_webrtc_no_upscale",
        name="3.1 WebRTC no-upscale",
    )
    adaptive_url = f"{config.hls_base_url}/{stream_id}_adaptive.m3u8"
    logger.info("Waiting for adaptive HLS manifest at %s", adaptive_url)
    manifest = wait_for_manifest(adaptive_url, verify_tls=config.verify_tls)
    heights = variant_heights(manifest)
    assert heights, f"Expected adaptive HLS variants for {stream_id}, but none were listed.\nManifest summary:\n{manifest_summary(manifest)}"
    assert max(heights) <= source_height, (
        f"Expected WebRTC ingest not to upscale above source height {source_height}, "
        f"but found variants {sorted(heights)}"
    )


@pytest.mark.webrtc
@pytest.mark.slow
def test_03_01_webrtc_ingest_generates_audio_and_adaptive_variants(
    api: ServerClient, config: TestConfig, browser
) -> None:
    stream_id, _, _ = start_webrtc_publish(
        api,
        config,
        browser,
        stream_prefix="streamtest_03_01_webrtc_variants",
        name="3.1 WebRTC variants",
    )
    adaptive_url = f"{config.hls_base_url}/{stream_id}_adaptive.m3u8"
    logger.info("Waiting for adaptive HLS manifest at %s", adaptive_url)
    manifest = wait_for_manifest(adaptive_url, verify_tls=config.verify_tls)
    assert not is_media_playlist(manifest), (
        "Expected an adaptive HLS master playlist after WebRTC ingest, "
        "but server returned a single media playlist.\n"
        f"Manifest URL: {adaptive_url}\n"
        f"Manifest summary:\n{manifest_summary(manifest)}"
    )
    heights = variant_heights(manifest)
    assert heights, f"Expected at least one adaptive variant for {stream_id}, but none were listed."
    variants = parse_variants(manifest)
    assert variants, f"Expected at least one adaptive variant entry for {stream_id}, but none were parsed."
    primary_variant_url = urljoin(adaptive_url, variants[0].uri)
    logger.info("Waiting for primary adaptive variant to become probeable at %s", primary_variant_url)
    probe = wait_for_stream_probe(primary_variant_url, timeout_seconds=90)
    assert video_streams(probe), "Full audio HLS variant has no video track"
    assert audio_streams(probe), "Primary adaptive HLS variant has no audio track"
