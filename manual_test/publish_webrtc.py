from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests
from selenium import webdriver
from selenium.common.exceptions import SessionNotCreatedException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

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
    parser.add_argument("--stream-name", help="Optional broadcast name")
    parser.add_argument("--api-token", help="Token used for application REST calls")
    parser.add_argument("--chrome-binary", help="Optional explicit Chrome/Chromium binary path")
    parser.add_argument("--chromedriver-binary", help="Optional explicit chromedriver binary path")
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
    parser.add_argument(
        "--skip-create-broadcast",
        action="store_true",
        help="Skip the REST broadcast create call before opening the publish page",
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
        rest_api_token=args.api_token,
    )


def create_broadcast(config: TestConfig, stream_id: str, stream_name: str | None) -> dict:
    token = config.rest_api_token
    if not token:
        raise ValueError("--api-token is required unless --skip-create-broadcast is set")

    headers = {
        "Authorization": token if token.lower().startswith("bearer ") else f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {"streamId": stream_id}
    if stream_name:
        payload["name"] = stream_name

    lookup_urls = [
        f"{config.normalized_server_url}/{config.application}/rest/v2/broadcast/{stream_id}",
        f"{config.normalized_server_url}/{config.application}/rest/v2/broadcasts/{stream_id}",
    ]
    for url in lookup_urls:
        logger.info("Checking existing broadcast via %s", url)
        try:
            response = requests.get(url, headers=headers, timeout=30, verify=config.verify_tls)
        except requests.RequestException:
            continue

        if response.ok:
            try:
                data = response.json() if response.content else {}
            except ValueError:
                data = {}
            if data:
                logger.info("Broadcast already exists for stream id %s, skipping create", stream_id)
                return data

        if response.status_code not in {404, 405}:
            body = response.text.strip()
            if len(body) > 300:
                body = body[:297] + "..."
            raise AssertionError(f"Broadcast lookup failed at {url}: HTTP {response.status_code} {body}")

    candidate_urls = [
        f"{config.normalized_server_url}/{config.application}/rest/v2/broadcast/create",
        f"{config.normalized_server_url}/{config.application}/rest/v2/broadcasts/create",
    ]
    last_error = ""
    for url in candidate_urls:
        logger.info("Creating broadcast via %s", url)
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30, verify=config.verify_tls)
        except requests.RequestException as exc:
            last_error = str(exc)
            continue

        if response.ok:
            return response.json() if response.content else {"success": True}

        if response.status_code in {404, 405}:
            last_error = f"HTTP {response.status_code} at {url}"
            continue

        body = response.text.strip()
        if len(body) > 300:
            body = body[:297] + "..."
        raise AssertionError(f"Broadcast create failed at {url}: HTTP {response.status_code} {body}")

    raise AssertionError(f"Broadcast create could not be completed. Last error: {last_error}")


def prepare_fake_capture_file(media_file: Path) -> Path:
    suffix = media_file.suffix.lower()
    if suffix in {".y4m", ".mjpeg", ".mjpg", ".jpeg", ".jpg"}:
        return media_file.resolve()

    mjpeg_file = media_file.with_suffix(".mjpeg")
    if mjpeg_file.exists() and mjpeg_file.stat().st_mtime >= media_file.stat().st_mtime:
        logger.info("Reusing cached MJPEG capture file: %s", mjpeg_file)
        return mjpeg_file.resolve()

    logger.info("Converting %s to cached MJPEG capture file %s", media_file, mjpeg_file)
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
        str(mjpeg_file),
    ]
    subprocess.run(command, check=True, timeout=600)
    return mjpeg_file.resolve()


def build_browser(
    config: TestConfig,
    fake_capture_file: Path | None,
    chrome_binary_override: str | None,
    chromedriver_binary_override: str | None,
):
    options = Options()
    temp_root = Path(tempfile.mkdtemp(prefix="chrome_runtime_", dir="/tmp"))
    data_path = temp_root / "data"
    cache_dir = temp_root / "cache"
    data_path.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    chrome_binary = (
        chrome_binary_override
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
        or shutil.which("google-chrome")
        or shutil.which("google-chrome-stable")
    )
    if chrome_binary:
        options.binary_location = chrome_binary
        logger.info("Using Chrome binary: %s", chrome_binary)
    if config.headless:
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
    options.add_argument("--autoplay-policy=no-user-gesture-required")
    options.add_argument("--use-fake-ui-for-media-stream")
    options.add_argument("--remote-debugging-port=0")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,720")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-setuid-sandbox")
    options.add_argument("--disable-crash-reporter")
    options.add_argument("--disable-breakpad")
    options.add_argument(f"--data-path={data_path}")
    options.add_argument(f"--disk-cache-dir={cache_dir}")
    options.add_argument("--enable-logging")
    options.add_argument("--v=1")
    if fake_capture_file is not None:
        options.add_argument("--use-fake-device-for-media-stream")
        logger.info("Using fake WebRTC capture file: %s", fake_capture_file)
        options.add_argument(f"--use-file-for-fake-video-capture={fake_capture_file}")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--no-sandbox")
    chromedriver_log = temp_root / "chromedriver.log"
    service = Service(executable_path=chromedriver_binary_override, log_output=str(chromedriver_log))
    try:
        return webdriver.Chrome(service=service, options=options), temp_root
    except SessionNotCreatedException as exc:
        details = ""
        if chromedriver_log.exists():
            details = chromedriver_log.read_text(encoding="utf-8", errors="replace")[-4000:]
        raise AssertionError(
            "Chrome session could not be created. "
            f"ChromeDriver log: {chromedriver_log}\n{details}"
        ) from exc


def main() -> int:
    args = parse_args()
    if args.camera_source == "file":
        if args.media_file is None:
            raise ValueError("--media-file is required when --camera-source file")
        if not args.media_file.exists():
            raise FileNotFoundError(f"Media file not found: {args.media_file}")

    config = build_config(args)
    fake_capture_file = None
    if args.camera_source == "file":
        fake_capture_file = prepare_fake_capture_file(args.media_file)
    browser, temp_root = build_browser(
        config,
        fake_capture_file,
        args.chrome_binary,
        args.chromedriver_binary,
    )
    page = StreamAppPage(browser, config)

    try:
        if not args.skip_create_broadcast:
            create_broadcast(config, args.stream_id, args.stream_name)

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
        shutil.rmtree(temp_root, ignore_errors=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
