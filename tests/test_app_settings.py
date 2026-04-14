from __future__ import annotations

from stream_testkit.app_settings import (
    DEFAULT_ABR_PROFILES,
    encoder_settings_list,
    encoder_settings_string,
    parse_encoder_settings_list,
    parse_encoder_settings_string,
    with_required_abr_profiles,
)


def test_with_required_abr_profiles_adds_missing_profiles() -> None:
    desired, changed = with_required_abr_profiles({"encoderSettingsString": "360,800000,64000"})

    profiles = parse_encoder_settings_string(desired["encoderSettingsString"])
    assert changed
    assert set(DEFAULT_ABR_PROFILES).issubset(profiles)
    assert profiles[360] == (800_000, 64_000)


def test_with_required_abr_profiles_keeps_complete_profiles_unchanged() -> None:
    settings = {
        "encoderSettingsString": (
            '[{"height":360,"videoBitrate":800000,"audioBitrate":64000,"forceEncode":false},'
            '{"height":540,"videoBitrate":1200000,"audioBitrate":96000,"forceEncode":false},'
            '{"height":720,"videoBitrate":2000000,"audioBitrate":128000,"forceEncode":false},'
            '{"height":1080,"videoBitrate":2500000,"audioBitrate":128000,"forceEncode":false}]'
        )
    }

    desired, changed = with_required_abr_profiles(settings)

    assert not changed
    assert desired == settings


def test_parse_encoder_settings_string_ignores_invalid_triplets() -> None:
    profiles = parse_encoder_settings_string("360,800000,64000,broken,values,here")

    assert profiles == {360: (800_000, 64_000)}


def test_parse_encoder_settings_string_supports_json_array() -> None:
    profiles = parse_encoder_settings_string(
        '[{"height":360,"videoBitrate":800000,"audioBitrate":64000,"forceEncode":false}]'
    )

    assert profiles == {360: (800_000, 64_000)}


def test_encoder_settings_string_uses_ant_media_triplet_format() -> None:
    value = encoder_settings_string({360: (800_000, 64_000), 540: (1_200_000, 96_000)})

    assert value == "360,800000,64000,540,1200000,96000"


def test_encoder_settings_list_uses_app_settings_payload_format() -> None:
    value = encoder_settings_list({360: (800_000, 64_000)})

    assert value == [{"height": 360, "videoBitrate": 800_000, "audioBitrate": 64_000, "forceEncode": False}]
    assert parse_encoder_settings_list(value) == {360: (800_000, 64_000)}
