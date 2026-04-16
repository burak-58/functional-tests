"""Run the full functional test suite."""

from __future__ import annotations

import argparse
import os
import sys

import pytest


SELECTED_TEST_FILES = [
    #"tests/test_01_01_test_harness_requirements.py",
    #"tests/test_01_02_initial_connectivity_configuration.py",
    "tests/test_02_01_rtmp_transcoding.py",
    "tests/test_02_02_feature_obligations.py",
    "tests/test_02_03_playback_protocol_latency_validation.py",
    "tests/test_03_01_webrtc_transcoding.py",
    "tests/test_03_02_webrtc_feature_obligations.py",
    "tests/test_03_03_webrtc_playback_protocol_latency_validation.py",
    #"tests/test_04_stress_test.py",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the functional test suite.")
    parser.add_argument("--server-url", required=True, help="Server base URL, for example https://host:5443")
    parser.add_argument("--user", help="Web panel user email")
    parser.add_argument("--password", help="Web panel password")
    parser.add_argument("--application", default="live", help="Application name, default: live")
    parser.add_argument("--media-file", help="Timestamped sample MP4 path for FFmpeg ingest")
    parser.add_argument("--rtmp-endpoint", help="Remote RTMP endpoint used for section 2.2 RTMP push")
    parser.add_argument("--snapshot-dir", help="Server-side snapshot directory to verify")
    parser.add_argument("--rest-api-token", help="JWT token for application REST endpoints")
    parser.add_argument("--duration-seconds", type=int, default=60, help="Default ingest/playback duration")
    parser.add_argument("--stress-streams", type=int, default=32, help="Number of streams for section 4")
    parser.add_argument("--stress-hours", type=float, default=1.0, help="Duration in hours for section 4")
    parser.add_argument("--headed", action="store_true", help="Run Chrome with a visible window")
    parser.add_argument("--headless", action="store_true", help="Run Chrome headless")
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER, help="Extra args passed to pytest after --")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.rest_api_token:
        missing = [name for name in ("user", "password") if not getattr(args, name)]
        if missing:
            joined = ", ".join(f"--{name.replace('_', '-')}" for name in missing)
            raise SystemExit(f"main.py: error: the following arguments are required unless --rest-api-token is provided: {joined}")

    os.environ["TESTKIT_SERVER_URL"] = args.server_url
    os.environ["TESTKIT_APPLICATION"] = args.application
    os.environ["TESTKIT_DURATION_SECONDS"] = str(args.duration_seconds)
    os.environ["TESTKIT_STRESS_STREAMS"] = str(args.stress_streams)
    os.environ["TESTKIT_STRESS_HOURS"] = str(args.stress_hours)
    if args.user:
        os.environ["TESTKIT_USER"] = args.user
    else:
        os.environ.pop("TESTKIT_USER", None)
    if args.password:
        os.environ["TESTKIT_PASSWORD"] = args.password
    else:
        os.environ.pop("TESTKIT_PASSWORD", None)
    if args.media_file:
        os.environ["TESTKIT_MEDIA_FILE"] = args.media_file
    if args.rtmp_endpoint:
        os.environ["TESTKIT_RTMP_ENDPOINT"] = args.rtmp_endpoint
    if args.snapshot_dir:
        os.environ["TESTKIT_SNAPSHOT_DIR"] = args.snapshot_dir
    if args.rest_api_token:
        os.environ["TESTKIT_REST_API_TOKEN"] = args.rest_api_token
    if args.headless:
        os.environ["TESTKIT_HEADLESS"] = "true"
    elif args.headed:
        os.environ["TESTKIT_HEADLESS"] = "false"

    extra = args.pytest_args[1:] if args.pytest_args[:1] == ["--"] else args.pytest_args
    return pytest.main([*SELECTED_TEST_FILES, *extra])


if __name__ == "__main__":
    sys.exit(main())
