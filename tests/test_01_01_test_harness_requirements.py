from __future__ import annotations

import os
import platform
import subprocess

import pytest

from stream_testkit.config import TestConfig
from stream_testkit.ffmpeg import require_tool


@pytest.mark.env
def test_01_01_harness_tools_available(config: TestConfig) -> None:
    require_tool("ffmpeg")
    require_tool("ffprobe")
    subprocess.run(["tesseract", "--version"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert config.media_file is None or config.media_file.exists(), f"Media file not found: {config.media_file}"


@pytest.mark.env
def test_01_01_hardware_baseline_visible() -> None:
    cpu = platform.processor() or platform.machine()
    assert cpu
    assert os.cpu_count() and os.cpu_count() >= 1
    gpu_check = subprocess.run(["bash", "-lc", "command -v nvidia-smi"], text=True, capture_output=True)
    if gpu_check.returncode == 0:
        subprocess.run(["nvidia-smi"], check=True, stdout=subprocess.DEVNULL)

