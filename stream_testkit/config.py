from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class TestConfig:
    __test__ = False

    server_url: str
    user: str
    password: str
    application: str = "live"
    media_file: Path | None = None
    rtmp_endpoint: str | None = None
    snapshot_dir: Path | None = None
    duration_seconds: int = 60
    stress_streams: int = 32
    stress_hours: float = 1.0
    headless: bool = True
    verify_tls: bool = False
    rest_api_token: str | None = None

    @property
    def normalized_server_url(self) -> str:
        return self.server_url.rstrip("/")

    @property
    def rtmp_base_url(self) -> str:
        host = self.normalized_server_url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
        return f"rtmp://{host}/{self.application}"

    @property
    def hls_base_url(self) -> str:
        return f"{self.normalized_server_url}/{self.application}/streams"

    @property
    def preview_base_url(self) -> str:
        return f"{self.normalized_server_url}/{self.application}/previews"

    def ll_hls_manifest_url(self, stream_id: str) -> str:
        return f"{self.normalized_server_url}/{self.application}/streams/ll-hls/{stream_id}/{stream_id}__master.m3u8"


def env_config() -> TestConfig:
    media_file = os.getenv("TESTKIT_MEDIA_FILE")
    snapshot_dir = os.getenv("TESTKIT_SNAPSHOT_DIR")
    return TestConfig(
        server_url=os.environ["TESTKIT_SERVER_URL"],
        user=os.getenv("TESTKIT_USER", ""),
        password=os.getenv("TESTKIT_PASSWORD", ""),
        application=os.getenv("TESTKIT_APPLICATION", "live"),
        media_file=Path(media_file) if media_file else None,
        rtmp_endpoint=os.getenv("TESTKIT_RTMP_ENDPOINT"),
        snapshot_dir=Path(snapshot_dir) if snapshot_dir else None,
        duration_seconds=int(os.getenv("TESTKIT_DURATION_SECONDS", "60")),
        stress_streams=int(os.getenv("TESTKIT_STRESS_STREAMS", "32")),
        stress_hours=float(os.getenv("TESTKIT_STRESS_HOURS", "1.0")),
        headless=os.getenv("TESTKIT_HEADLESS", "false").lower() in {"1", "true", "yes"},
        verify_tls=os.getenv("TESTKIT_VERIFY_TLS", "false").lower() in {"1", "true", "yes"},
        rest_api_token=os.getenv("TESTKIT_REST_API_TOKEN"),
    )
