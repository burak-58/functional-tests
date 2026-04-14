from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from io import BytesIO
import logging
from pathlib import Path
import re
import tempfile
from typing import Any

from PIL import Image, ImageEnhance, ImageOps
import pytesseract

logger = logging.getLogger(__name__)

TIMESTAMP_PATTERN = re.compile(
    r"(?P<hour>\d{1,2})[:.](?P<minute>\d{1,2})[:.](?P<second>\d{1,2})(?:[.,](?P<millis>\d{1,3}))?"
)


@dataclass(frozen=True)
class OcrResult:
    text: str
    matched_text: str
    observed_at: datetime
    embedded_time: datetime
    latency_seconds: float
    raw_image_path: Path
    processed_image_path: Path


def extract_broadcast_start_time(broadcast: dict[str, Any]) -> datetime | None:
    for key in ("absoluteStartTimeMs", "startTime", "date"):
        value = broadcast.get(key)
        parsed = _parse_epoch_ms(value)
        if parsed is not None and parsed.year >= 2000:
            return parsed
    return None


def _parse_epoch_ms(value: Any) -> datetime | None:
    if value in (None, "", 0, "0"):
        return None
    try:
        integer = int(value)
    except (TypeError, ValueError):
        return None
    if integer <= 0:
        return None
    if integer < 10_000_000_000:
        integer *= 1000
    return datetime.fromtimestamp(integer / 1000.0)


def measure_latency_from_frame(
    image_bytes: bytes,
    *,
    stream_id: str,
    protocol: str,
    broadcast_started_at: datetime | None,
    observed_at: datetime | None = None,
) -> OcrResult:
    observed_at = observed_at or datetime.now()
    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    processed_variants = _prepare_timestamp_crops(image)
    raw_path, processed_path = _write_debug_images(
        image,
        processed_variants[0],
        stream_id=stream_id,
        protocol=protocol,
    )
    normalized, match = _extract_timestamp_text(processed_variants)
    if match is None:
        raise AssertionError(
            f"OCR could not extract a timestamp from playback frame for {stream_id}. "
            f"Raw OCR text: {normalized!r}. Raw image: {raw_path}. Processed image: {processed_path}"
        )
    ocr_elapsed = _timestamp_to_timedelta(match.groupdict())
    if broadcast_started_at is not None:
        current_since_start = observed_at - broadcast_started_at
        embedded_time = broadcast_started_at + ocr_elapsed
        latency_seconds = (current_since_start - ocr_elapsed).total_seconds()
    else:
        embedded_time = observed_at.replace(
            hour=int(match.group("hour") or 0),
            minute=int(match.group("minute") or 0),
            second=int(match.group("second") or 0),
            microsecond=int((match.group("millis") or "0").ljust(3, "0")[:3]) * 1000,
        )
        latency_seconds = 0.0
    return OcrResult(
        text=normalized,
        matched_text=match.group(0),
        observed_at=observed_at,
        embedded_time=embedded_time,
        latency_seconds=latency_seconds,
        raw_image_path=raw_path,
        processed_image_path=processed_path,
    )


def _prepare_timestamp_crops(image: Image.Image) -> list[Image.Image]:
    width, height = image.size
    crop = image.crop((int(width * 0.01), int(height * 0.01), int(width * 0.38), int(height * 0.14)))
    grayscale = ImageOps.grayscale(crop)
    contrast = ImageEnhance.Contrast(grayscale).enhance(2.5)
    enlarged = contrast.resize((contrast.width * 5, contrast.height * 5))
    return [
        enlarged,
        ImageOps.invert(enlarged),
        enlarged.point(lambda pixel: 255 if pixel > 170 else 0),
        ImageOps.invert(enlarged.point(lambda pixel: 255 if pixel > 145 else 0)),
    ]


def _extract_timestamp_text(images: list[Image.Image]) -> tuple[str, re.Match[str] | None]:
    attempts: list[str] = []
    best_match: re.Match[str] | None = None
    best_text = ""
    for processed in images:
        for psm in ("7", "6", "13"):
            text = pytesseract.image_to_string(
                processed,
                config=f"--psm {psm} -c tessedit_char_whitelist=0123456789:.,",
            ).strip()
            normalized = " ".join(text.split())
            if normalized:
                attempts.append(normalized)
            match = _best_timestamp_match(normalized)
            if match is not None and len(match.group(0)) > len(best_text):
                best_match = match
                best_text = normalized
    if best_match is not None:
        return best_text, best_match
    return " | ".join(filter(None, attempts)), None


def _best_timestamp_match(text: str) -> re.Match[str] | None:
    best: re.Match[str] | None = None
    for match in TIMESTAMP_PATTERN.finditer(text):
        if best is None or len(match.group(0)) > len(best.group(0)):
            best = match
    return best


def _write_debug_images(
    raw_image: Image.Image,
    processed_image: Image.Image,
    *,
    stream_id: str,
    protocol: str,
) -> tuple[Path, Path]:
    debug_dir = Path(tempfile.gettempdir()) / "latency_debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    raw_path = debug_dir / f"{stream_id}_{protocol}_{stamp}_raw.png"
    processed_path = debug_dir / f"{stream_id}_{protocol}_{stamp}_ocr.png"
    raw_image.save(raw_path)
    processed_image.save(processed_path)
    return raw_path, processed_path
def _timestamp_to_millis(groups: dict[str, str | None]) -> int:
    _validate_timestamp_groups(groups)
    millis = int((groups.get("millis") or "0").ljust(3, "0")[:3])
    return (
        ((int(groups["hour"] or 0) * 60 + int(groups["minute"] or 0)) * 60 + int(groups["second"] or 0)) * 1000
        + millis
    )


def _timestamp_to_timedelta(groups: dict[str, str | None]) -> timedelta:
    return timedelta(milliseconds=_timestamp_to_millis(groups))


def _validate_timestamp_groups(groups: dict[str, str | None]) -> None:
    hour = int(groups["hour"] or 0)
    minute = int(groups["minute"] or 0)
    second = int(groups["second"] or 0)
    millis = int((groups.get("millis") or "0").ljust(3, "0")[:3])
    if not 0 <= hour <= 23:
        raise AssertionError(f"OCR extracted invalid hour component: {hour}")
    if not 0 <= minute <= 59:
        raise AssertionError(f"OCR extracted invalid minute component: {minute}")
    if not 0 <= second <= 59:
        raise AssertionError(f"OCR extracted invalid second component: {second}")
    if not 0 <= millis <= 999:
        raise AssertionError(f"OCR extracted invalid millisecond component: {millis}")
