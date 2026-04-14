from __future__ import annotations

import pytest

from stream_testkit.app_settings import (
    DEFAULT_ABR_PROFILES,
    encoder_settings_list,
    encoder_settings_string,
    parse_encoder_settings_list,
    parse_encoder_settings_string,
    with_required_abr_profiles,
)
from stream_testkit.config import TestConfig
from stream_testkit.rest_client import ServerClient


@pytest.mark.env
def test_01_02_authenticate_and_application_exists(api: ServerClient, config: TestConfig) -> None:
    applications = api.applications()
    assert config.application in applications


@pytest.mark.env
def test_01_02_system_settings_and_gpu_stats_available(api: ServerClient) -> None:
    settings = api.system_settings()
    resources = api.system_resources()
    assert settings
    assert resources
    assert any("gpu" in key.lower() for key in resources.keys()), f"GPU stats were not exposed: {resources.keys()}"


@pytest.mark.env
def test_01_02_live_application_settings_can_be_read_and_updated(api: ServerClient) -> None:
    settings = api.get_application_settings()
    assert isinstance(settings, dict)
    desired, _ = with_required_abr_profiles(settings)
    desired["encoderSettings"] = encoder_settings_list(DEFAULT_ABR_PROFILES)
    desired["encoderSettingsString"] = encoder_settings_string(DEFAULT_ABR_PROFILES)
    encoder_changed = settings.get("encoderSettingsString") != desired["encoderSettingsString"]
    desired["generatePreview"] = True
    desired["createPreviewPeriod"] = 5000
    desired["previewOverwrite"] = True
    desired["previewFormat"] = "png"
    desired["mp4MuxingEnabled"] = True
    desired["addDateTimeToMp4FileName"] = False
    desired["h264Enabled"] = True
    desired["aacEncodingEnabled"] = True
    response = api.set_application_settings(desired)
    assert response
    reread = api.get_application_settings()
    assert reread
    abr_profiles = parse_encoder_settings_string(reread.get("encoderSettingsString"))
    abr_profiles.update(parse_encoder_settings_list(reread.get("encoderSettings")))
    assert DEFAULT_ABR_PROFILES.items() <= abr_profiles.items(), (
        "Required adaptive bitrate profiles do not match after application settings update. "
        f"Missing: {sorted(set(DEFAULT_ABR_PROFILES) - set(abr_profiles))}; "
        f"Mismatched: {sorted(height for height, profile in DEFAULT_ABR_PROFILES.items() if abr_profiles.get(height) != profile)}; "
        f"encoderSettings: {reread.get('encoderSettings')!r}; "
        f"encoderSettingsString: {reread.get('encoderSettingsString')!r}; "
        f"desired_encoderSettings: {desired.get('encoderSettings')!r}; "
        f"desired_encoderSettingsString: {desired.get('encoderSettingsString')!r}; "
        f"encoder_updated_this_run: {encoder_changed}"
    )
    assert reread.get("generatePreview") is True, f"generatePreview was not enabled: {reread.get('generatePreview')!r}"
    assert int(reread.get("createPreviewPeriod", 0) or 0) == 5000, (
        "createPreviewPeriod did not persist after application settings update. "
        f"Expected 5000, got {reread.get('createPreviewPeriod')!r}"
    )
    assert reread.get("previewOverwrite") is True, (
        "previewOverwrite was not enabled after application settings update. "
        f"Got {reread.get('previewOverwrite')!r}"
    )
    assert str(reread.get("previewFormat", "")).lower() == "png", (
        "previewFormat did not persist as png after application settings update. "
        f"Got {reread.get('previewFormat')!r}"
    )
    assert reread.get("mp4MuxingEnabled") is True, (
        "mp4MuxingEnabled was not enabled after application settings update. "
        f"Got {reread.get('mp4MuxingEnabled')!r}"
    )
    assert reread.get("addDateTimeToMp4FileName") is False, (
        "addDateTimeToMp4FileName was not disabled after application settings update. "
        f"Got {reread.get('addDateTimeToMp4FileName')!r}"
    )
    assert reread.get("h264Enabled") is True, (
        "h264Enabled was not enabled after application settings update. "
        f"Got {reread.get('h264Enabled')!r}"
    )
    assert reread.get("aacEncodingEnabled") is True, (
        "aacEncodingEnabled was not enabled after application settings update. "
        f"Got {reread.get('aacEncodingEnabled')!r}"
    )
