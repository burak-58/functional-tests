from __future__ import annotations

import logging
import os

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from stream_testkit.config import TestConfig, env_config
from stream_testkit.ffmpeg import ensure_webrtc_capture_file
from stream_testkit.rest_client import ServerClient

logger = logging.getLogger(__name__)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--server-url", default=os.getenv("TESTKIT_SERVER_URL"), help="Server base URL")
    parser.addoption("--user", default=os.getenv("TESTKIT_USER"), help="Web panel user email")
    parser.addoption("--password", default=os.getenv("TESTKIT_PASSWORD"), help="Web panel password")
    parser.addoption("--application", default=os.getenv("TESTKIT_APPLICATION", "live"), help="Application name")
    parser.addoption("--media-file", default=os.getenv("TESTKIT_MEDIA_FILE"), help="Timestamped MP4 test source")
    parser.addoption("--rtmp-endpoint", default=os.getenv("TESTKIT_RTMP_ENDPOINT"), help="Remote RTMP endpoint")
    parser.addoption("--snapshot-dir", default=os.getenv("TESTKIT_SNAPSHOT_DIR"), help="Server-side snapshot directory")
    parser.addoption("--rest-api-token", default=os.getenv("TESTKIT_REST_API_TOKEN"), help="JWT token for application REST endpoints")
    parser.addoption("--duration-seconds", default=os.getenv("TESTKIT_DURATION_SECONDS", "60"), help="Default duration")
    parser.addoption("--stress-streams", default=os.getenv("TESTKIT_STRESS_STREAMS", "32"), help="Stress stream count")
    parser.addoption("--stress-hours", default=os.getenv("TESTKIT_STRESS_HOURS", "1"), help="Stress duration in hours")
    parser.addoption("--headed", action="store_true", help="Run Chrome headed")
    parser.addoption("--headless", action="store_true", help="Run Chrome headless")


@pytest.fixture(scope="session")
def config(pytestconfig: pytest.Config) -> TestConfig:
    required = ["server_url", "user", "password"]
    missing = [name for name in required if not pytestconfig.getoption(name)]
    if missing:
        pytest.fail("Missing required option(s): " + ", ".join(f"--{name.replace('_', '-')}" for name in missing))
    os.environ["TESTKIT_SERVER_URL"] = pytestconfig.getoption("server_url")
    os.environ["TESTKIT_USER"] = pytestconfig.getoption("user")
    os.environ["TESTKIT_PASSWORD"] = pytestconfig.getoption("password")
    os.environ["TESTKIT_APPLICATION"] = pytestconfig.getoption("application")
    if pytestconfig.getoption("media_file"):
        os.environ["TESTKIT_MEDIA_FILE"] = pytestconfig.getoption("media_file")
    if pytestconfig.getoption("rtmp_endpoint"):
        os.environ["TESTKIT_RTMP_ENDPOINT"] = pytestconfig.getoption("rtmp_endpoint")
    if pytestconfig.getoption("snapshot_dir"):
        os.environ["TESTKIT_SNAPSHOT_DIR"] = pytestconfig.getoption("snapshot_dir")
    if pytestconfig.getoption("rest_api_token"):
        os.environ["TESTKIT_REST_API_TOKEN"] = pytestconfig.getoption("rest_api_token")
    os.environ["TESTKIT_DURATION_SECONDS"] = str(pytestconfig.getoption("duration_seconds"))
    os.environ["TESTKIT_STRESS_STREAMS"] = str(pytestconfig.getoption("stress_streams"))
    os.environ["TESTKIT_STRESS_HOURS"] = str(pytestconfig.getoption("stress_hours"))
    if pytestconfig.getoption("headless"):
        os.environ["TESTKIT_HEADLESS"] = "true"
    elif pytestconfig.getoption("headed"):
        os.environ["TESTKIT_HEADLESS"] = "false"
    return env_config()


@pytest.fixture(scope="session")
def api(config: TestConfig) -> ServerClient:
    client = ServerClient(config)
    client.authenticate()
    return client


@pytest.fixture()
def browser(config: TestConfig):
    options = Options()
    if config.headless:
        options.add_argument("--headless=new")
    options.add_argument("--autoplay-policy=no-user-gesture-required")
    options.add_argument("--use-fake-ui-for-media-stream")
    options.add_argument("--use-fake-device-for-media-stream")
    if config.media_file:
        fake_capture_file = ensure_webrtc_capture_file(config.media_file).resolve()
        logger.info("Chrome fake WebRTC video capture file: %s", fake_capture_file)
        options.add_argument(f"--use-file-for-fake-video-capture={fake_capture_file}")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--no-sandbox")
    driver = webdriver.Chrome(options=options)
    try:
        yield driver
    finally:
        driver.quit()
