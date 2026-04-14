from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from stream_testkit.config import TestConfig
from stream_testkit.pages import StreamAppPage


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("manual_test.publish_webrtc")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Open the publish page and start a WebRTC publish session."
    )
    parser.add_argument("server_url", help="Server base URL, for example: https://host:5443")
    parser.add_argument("--application", default="live", help="Application name")
    parser.add_argument(
        "--camera-source",
        choices=("file", "device"),
        default="file",
        help="Use a media file with Chrome fake camera, or the system default webcam/virtual webcam",
    )
    parser.add_argument("--media-file", type=Path, help="Media file used when --camera-source file")
    parser.add_argument("--stream-id", default="test_publish", help="Stream id to publish")
    parser.add_argument("--headless", action="store_true", help="Run Chrome headless")
    parser.add_argument(
        "--verify-tls",
        action="store_true",
        help="Verify TLS certificate instead of ignoring certificate errors",
    )
    parser.add_argument(
        "--duration-seconds",
        type=int,
        default=0,
        help="If > 0, keep publishing for this many seconds; otherwise wait until Ctrl+C",
    )
    return parser.parse_args()


def build_config(args: argparse.Namespace) -> TestConfig:
    return TestConfig(
        server_url=args.server_url,
        user="",
        password="",
        application=args.application,
        media_file=args.media_file,
        headless=args.headless,
        verify_tls=args.verify_tls,
    )


def prepare_fake_capture_file(media_file: Path) -> tuple[Path, Path | None]:
    suffix = media_file.suffix.lower()
    if suffix in {".y4m", ".mjpeg", ".mjpg", ".jpeg", ".jpg"}:
        return media_file.resolve(), None

    temp_dir = Path(tempfile.mkdtemp(prefix="webrtc_capture_"))
    temp_capture_file = temp_dir / f"{media_file.stem}.mjpeg"
    logger.info("Converting %s to temporary MJPEG capture file %s", media_file, temp_capture_file)
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(media_file),
        "-an",
        "-q:v",
        "3",
        "-f",
        "mjpeg",
        str(temp_capture_file),
    ]
    subprocess.run(command, check=True, timeout=600)
    return temp_capture_file.resolve(), temp_dir


def build_browser(config: TestConfig, fake_capture_file: Path | None):
    options = Options()
    if config.headless:
        options.add_argument("--headless=new")
    options.add_argument("--autoplay-policy=no-user-gesture-required")
    options.add_argument("--use-fake-ui-for-media-stream")
    if fake_capture_file is not None:
        options.add_argument("--use-fake-device-for-media-stream")
        logger.info("Using fake WebRTC capture file: %s", fake_capture_file)
        options.add_argument(f"--use-file-for-fake-video-capture={fake_capture_file}")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--no-sandbox")
    return webdriver.Chrome(options=options)


def main() -> int:
    args = parse_args()
    if args.camera_source == "file":
        if args.media_file is None:
            raise ValueError("--media-file is required when --camera-source file")
        if not args.media_file.exists():
            raise FileNotFoundError(f"Media file not found: {args.media_file}")

    config = build_config(args)
    temp_dir = None
    fake_capture_file = None
    if args.camera_source == "file":
        fake_capture_file, temp_dir = prepare_fake_capture_file(args.media_file)
    browser = build_browser(config, fake_capture_file)
    page = StreamAppPage(browser, config)

    try:
        logger.info("Opening publish page")
        page.open_publish_page(args.stream_id)

        logger.info("Starting WebRTC publish")
        page.start_publishing()
        page.wait_until_video_playing(in_publish_frame=True)

        print(f"Publishing started for stream '{args.stream_id}'")
        print(f"Publish page: {config.normalized_server_url}/{config.application}/index.html?id={args.stream_id}")
        print("Stop with Ctrl+C")

        if args.duration_seconds > 0:
            time.sleep(args.duration_seconds)
        else:
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping publish due to Ctrl+C")
    finally:
        try:
            page.stop_publishing()
        except Exception as exc:
            logger.warning("Could not stop publishing cleanly: %s", exc)
        browser.quit()
        if temp_dir is not None:
            for path in temp_dir.iterdir():
                path.unlink(missing_ok=True)
            temp_dir.rmdir()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
