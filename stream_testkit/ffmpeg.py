from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any


def require_tool(name: str) -> None:
    subprocess.run([name, "-version"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def start_rtmp_ingest(media_file: Path, rtmp_url: str, *, video_bitrate: str, resolution: str, fps: int) -> subprocess.Popen[str]:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-re",
        "-stream_loop",
        "-1",
        "-i",
        str(media_file),
        "-vf",
        f"scale={resolution},fps={fps}",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-b:v",
        video_bitrate,
        "-maxrate",
        video_bitrate,
        "-bufsize",
        str(int(video_bitrate.rstrip("k")) * 2) + "k" if video_bitrate.endswith("k") else video_bitrate,
        "-c:a",
        "aac",
        "-f",
        "flv",
        rtmp_url,
    ]
    return subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def capture_media_frame(media_file: Path, *, offset_seconds: float = 0.0) -> bytes:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
    ]
    if offset_seconds > 0:
        command.extend(["-ss", str(offset_seconds)])
    command.extend(
        [
            "-i",
            str(media_file),
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-vcodec",
            "png",
            "-",
        ]
    )
    completed = subprocess.run(command, check=True, capture_output=True, timeout=30)
    return completed.stdout


def ensure_webrtc_capture_file(media_file: Path) -> Path:
    if media_file.suffix.lower() == ".y4m":
        return media_file
    output_path = media_file.with_suffix(".webrtc.y4m")
    if output_path.exists() and output_path.stat().st_mtime >= media_file.stat().st_mtime:
        return output_path
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(media_file),
        "-an",
        "-pix_fmt",
        "yuv420p",
        "-f",
        "yuv4mpegpipe",
        str(output_path),
    ]
    subprocess.run(command, check=True, timeout=600)
    return output_path


def stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def wait_for_stream_probe(
    url: str, timeout_seconds: int = 60, process: subprocess.Popen[str] | None = None
) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        if process is not None and process.poll() is not None:
            _, stderr = process.communicate(timeout=1)
            raise AssertionError(f"ffmpeg ingest exited early with code {process.returncode}:\n{stderr[-2000:]}")
        try:
            return ffprobe(url)
        except subprocess.CalledProcessError as exc:
            last_error = exc.stderr or str(exc)
            time.sleep(2)
    raise AssertionError(f"Stream was not probeable before timeout: {url}\n{last_error}")


def ffprobe(url: str) -> dict[str, Any]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        url,
    ]
    completed = subprocess.run(command, check=True, text=True, capture_output=True, timeout=30)
    return json.loads(completed.stdout)


def video_streams(probe: dict[str, Any]) -> list[dict[str, Any]]:
    return [stream for stream in probe.get("streams", []) if stream.get("codec_type") == "video"]


def audio_streams(probe: dict[str, Any]) -> list[dict[str, Any]]:
    return [stream for stream in probe.get("streams", []) if stream.get("codec_type") == "audio"]
