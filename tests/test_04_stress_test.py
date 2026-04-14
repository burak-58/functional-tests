from __future__ import annotations

import time
import uuid

import pytest

from stream_testkit.config import TestConfig
from stream_testkit.ffmpeg import start_rtmp_ingest, stop_process
from stream_testkit.rest_client import ServerClient


@pytest.mark.stress
@pytest.mark.slow
def test_04_32_simultaneous_active_streams(api: ServerClient, config: TestConfig) -> None:
    if not config.media_file:
        pytest.skip("--media-file is required for stress test")
    processes = []
    stream_ids = [f"streamtest_04_stress_{index}_{uuid.uuid4().hex[:8]}" for index in range(config.stress_streams)]
    try:
        for stream_id in stream_ids:
            api.create_broadcast(stream_id, "4 Stress test")
            processes.append(
                start_rtmp_ingest(config.media_file, f"{config.rtmp_base_url}/{stream_id}", video_bitrate="6000k", resolution="1920:1080", fps=30)
            )
        time.sleep(config.stress_hours * 3600)
        for stream_id in stream_ids:
            broadcast = api.get_broadcast(stream_id)
            assert broadcast
    finally:
        for process in processes:
            stop_process(process)

