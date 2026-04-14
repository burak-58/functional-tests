from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Variant:
    uri: str
    bandwidth: int | None
    resolution: tuple[int, int] | None


def fetch_manifest(url: str, *, verify_tls: bool = False) -> str:
    logger.info("Manifest query %s", url)
    try:
        response = requests.get(url, timeout=30, verify=verify_tls)
        response.raise_for_status()
    except requests.RequestException as exc:
        response = getattr(exc, "response", None)
        if response is not None:
            body = response.text.strip().replace("\n", " ")[:300]
            logger.warning("Manifest query %s -> HTTP %s: %s", url, response.status_code, body)
        else:
            logger.warning("Manifest query %s -> request failed: %s", url, exc)
        raise
    logger.info("Manifest query %s -> HTTP %s", url, response.status_code)
    return response.text


def wait_for_manifest(url: str, *, verify_tls: bool = False, timeout_seconds: int = 90) -> str:
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        try:
            return fetch_manifest(url, verify_tls=verify_tls)
        except requests.RequestException as exc:
            response = getattr(exc, "response", None)
            if response is not None:
                body = response.text.strip().replace("\n", " ")[:300]
                last_error = f"HTTP {response.status_code}: {body}"
            else:
                last_error = str(exc)
            time.sleep(2)
    logger.warning("Manifest query %s -> timed out after %ss: %s", url, timeout_seconds, last_error)
    raise AssertionError(f"Manifest was not available before timeout: {url}\nLast error: {last_error}")


def parse_variants(manifest_text: str) -> list[Variant]:
    variants: list[Variant] = []
    lines = [line.strip() for line in manifest_text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if not line.startswith("#EXT-X-STREAM-INF"):
            continue
        uri = lines[index + 1] if index + 1 < len(lines) else ""
        bandwidth_match = re.search(r"BANDWIDTH=(\d+)", line)
        resolution_match = re.search(r"RESOLUTION=(\d+)x(\d+)", line)
        variants.append(
            Variant(
                uri=uri,
                bandwidth=int(bandwidth_match.group(1)) if bandwidth_match else None,
                resolution=(int(resolution_match.group(1)), int(resolution_match.group(2))) if resolution_match else None,
            )
        )
    return variants


def is_media_playlist(manifest_text: str) -> bool:
    return "#EXTINF:" in manifest_text and "#EXT-X-STREAM-INF" not in manifest_text


def manifest_summary(manifest_text: str, *, max_lines: int = 8) -> str:
    lines = [line.strip() for line in manifest_text.splitlines() if line.strip()]
    return "\n".join(lines[:max_lines])


def variant_heights(manifest_text: str) -> set[int]:
    return {variant.resolution[1] for variant in parse_variants(manifest_text) if variant.resolution}
