from __future__ import annotations

import subprocess
import uuid

import pytest

from stream_testkit.config import TestConfig
from stream_testkit.ffmpeg import audio_streams, start_rtmp_ingest, stop_process, video_streams, wait_for_stream_probe
from stream_testkit.manifest import fetch_manifest, is_media_playlist, manifest_summary, variant_heights, wait_for_manifest
from stream_testkit.rest_client import ServerClient


def _require_media(config: TestConfig) -> None:
    if not config.media_file:
        pytest.skip("--media-file is required for RTMP ingest tests")


def _assert_ingest_still_running(process: subprocess.Popen[str], stream_id: str) -> None:
    if process.poll() is None:
        return

    _, stderr = process.communicate(timeout=1)
    raise AssertionError(f"ffmpeg ingest exited early for {stream_id} with code {process.returncode}:\n{stderr[-2000:]}")


@pytest.mark.rtmp
@pytest.mark.slow
def test_02_01_720p_ingest_does_not_generate_1080p_variant(api: ServerClient, config: TestConfig) -> None:
    _require_media(config)
    stream_id = f"streamtest_02_01_720p_{uuid.uuid4().hex[:8]}"
    api.create_broadcast(stream_id, "2.1 720p no-upscale")
    process = start_rtmp_ingest(config.media_file, f"{config.rtmp_base_url}/{stream_id}", video_bitrate="6000k", resolution="1280:720", fps=30)
    try:
        _assert_ingest_still_running(process, stream_id)
        manifest = wait_for_manifest(f"{config.hls_base_url}/{stream_id}_adaptive.m3u8", verify_tls=config.verify_tls)
        assert 1080 not in variant_heights(manifest)
    finally:
        stop_process(process)


@pytest.mark.rtmp
@pytest.mark.slow
def test_02_01_1080p_ingest_generates_audio_and_silenced_variants(api: ServerClient, config: TestConfig) -> None:
    _require_media(config)
    stream_id = f"streamtest_02_01_1080p_{uuid.uuid4().hex[:8]}"
    api.create_broadcast(stream_id, "2.1 1080p variants")
    process = start_rtmp_ingest(config.media_file, f"{config.rtmp_base_url}/{stream_id}", video_bitrate="6000k", resolution="1920:1080", fps=30)
    try:
        full_audio_url = f"{config.hls_base_url}/{stream_id}.m3u8"
        _assert_ingest_still_running(process, stream_id)
        probe = wait_for_stream_probe(full_audio_url, timeout_seconds=90, process=process)
        assert video_streams(probe), "Full audio HLS variant has no video track"
        assert audio_streams(probe), "Full audio HLS variant has no audio track"
        adaptive_url = f"{config.hls_base_url}/{stream_id}_adaptive.m3u8"
        manifest = wait_for_manifest(adaptive_url, verify_tls=config.verify_tls)
        heights = variant_heights(manifest)
        assert not is_media_playlist(manifest), (
            "Expected an adaptive HLS master playlist with 360p/540p/720p/1080p variants, "
            "but server returned a single media playlist. Check adaptive bitrate/transcoding settings.\n"
            f"Manifest URL: {adaptive_url}\n"
            f"Manifest summary:\n{manifest_summary(manifest)}"
        )
        assert {360, 540, 720, 1080}.issubset(heights), f"Missing expected variants. Found heights: {sorted(heights)}"
    finally:
        stop_process(process)
