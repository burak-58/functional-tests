from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any


DEFAULT_ABR_PROFILES: dict[int, tuple[int, int]] = {
    360: (800_000, 64_000),
    540: (1_200_000, 96_000),
    720: (2_000_000, 128_000),
    1080: (2_500_000, 128_000),
}


def encoder_settings_list(profiles: Mapping[int, tuple[int, int]]) -> list[dict[str, int | bool]]:
    values: list[dict[str, int | bool]] = []
    for height in sorted(profiles):
        video_bitrate, audio_bitrate = profiles[height]
        values.append(
            {
                "height": height,
                "videoBitrate": video_bitrate,
                "audioBitrate": audio_bitrate,
                "forceEncode": False,
            }
        )
    return values


def parse_encoder_settings_list(value: Any) -> dict[int, tuple[int, int]]:
    if not isinstance(value, list):
        return {}

    profiles: dict[int, tuple[int, int]] = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        try:
            height = int(item["height"])
            video_bitrate = int(item["videoBitrate"])
            audio_bitrate = int(item["audioBitrate"])
        except (KeyError, TypeError, ValueError):
            continue
        profiles[height] = (video_bitrate, audio_bitrate)
    return profiles


def parse_encoder_settings_string(value: Any) -> dict[int, tuple[int, int]]:
    if not isinstance(value, str) or not value.strip():
        return {}

    if value.strip().startswith("["):
        return _parse_encoder_settings_json(value)

    parts = [part.strip() for part in value.split(",") if part.strip()]
    profiles: dict[int, tuple[int, int]] = {}
    for index in range(0, len(parts) - 2, 3):
        try:
            height = int(parts[index])
            video_bitrate = int(parts[index + 1])
            audio_bitrate = int(parts[index + 2])
        except ValueError:
            continue
        profiles[height] = (video_bitrate, audio_bitrate)
    return profiles


def _parse_encoder_settings_json(value: str) -> dict[int, tuple[int, int]]:
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, list):
        return {}

    return parse_encoder_settings_list(data)


def encoder_settings_string(profiles: Mapping[int, tuple[int, int]]) -> str:
    values: list[str] = []
    for height in sorted(profiles):
        video_bitrate, audio_bitrate = profiles[height]
        values.extend((str(height), str(video_bitrate), str(audio_bitrate)))
    return ",".join(values)


def with_required_abr_profiles(settings: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
    desired = dict(settings)
    profiles = parse_encoder_settings_string(desired.get("encoderSettingsString"))
    missing_heights = set(DEFAULT_ABR_PROFILES) - set(profiles)
    if not missing_heights:
        return desired, False

    for height in missing_heights:
        profiles[height] = DEFAULT_ABR_PROFILES[height]
    desired["encoderSettingsString"] = encoder_settings_string(profiles)
    return desired, True
