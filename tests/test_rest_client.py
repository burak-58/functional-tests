from __future__ import annotations

from typing import Any

import pytest
import requests

from stream_testkit.config import TestConfig as Config
from stream_testkit.rest_client import ServerClient


class StaticSession:
    def __init__(self, response: requests.Response) -> None:
        self.response = response
        self.verify = False
        self.requests: list[tuple[str, str, dict[str, Any]]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        captured: dict[str, Any] = {}
        if kwargs.get("headers"):
            captured["headers"] = dict(kwargs["headers"])
        if "json" in kwargs:
            captured["json"] = kwargs["json"]
        self.requests.append((method, url, captured))
        return self.response


class FailingSession:
    def __init__(self, error: requests.RequestException) -> None:
        self.error = error
        self.verify = False

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        raise self.error


def _client(response: requests.Response) -> ServerClient:
    config = Config(server_url="https://server.example.test", user="user@example.test", password="secret")
    client = ServerClient(config)
    client.session = StaticSession(response)  # type: ignore[assignment]
    return client


def _response(status_code: int, body: bytes) -> requests.Response:
    response = requests.Response()
    response.status_code = status_code
    response._content = body
    response.url = "https://server.example.test/rest/v2/test"
    return response


def test_authenticate_fails_when_server_rejects_credentials() -> None:
    client = _client(_response(200, b'{"success": false, "message": "Invalid user or password"}'))

    with pytest.raises(AssertionError, match="Invalid user or password"):
        client.authenticate()


def test_authenticate_warns_when_supplied_password_looks_pre_hashed() -> None:
    client = _client(_response(200, b'{"success": false, "message": "Invalid user or password"}'))
    client.config = Config(
        server_url=client.config.server_url,
        user=client.config.user,
        password="05a671c66aefea124cc08b76ea6d30bb",
    )

    with pytest.raises(AssertionError, match="raw panel password"):
        client.authenticate()


def test_authenticate_reports_unreachable_server_url() -> None:
    config = Config(server_url="http://localhost:5080", user="user@example.test", password="secret")
    client = ServerClient(config)
    client.session = FailingSession(requests.ConnectionError("connection refused"))  # type: ignore[assignment]

    with pytest.raises(AssertionError, match=r"--server-url points to the web panel base URL.*https://SERVER_HOST:5443"):
        client.authenticate()


def test_authenticate_is_skipped_when_rest_api_token_is_configured() -> None:
    client = _client(_response(500, b'{"success": false}'))
    client.config = Config(
        server_url=client.config.server_url,
        user="",
        password="",
        rest_api_token="token-value",
    )

    assert client.authenticate() == {"success": True, "auth": "token"}

    assert isinstance(client.session, StaticSession)
    assert client.session.requests == []


def test_authenticate_uses_panel_credentials_even_when_rest_api_token_is_configured() -> None:
    client = _client(_response(200, b'{"success": true}'))
    client.config = Config(
        server_url=client.config.server_url,
        user="user@example.test",
        password="secret",
        rest_api_token="token-value",
    )

    client.authenticate()

    assert isinstance(client.session, StaticSession)
    assert client.session.requests == [
        (
            "POST",
            "https://server.example.test/rest/v2/users/authenticate",
            {"json": {"email": "user@example.test", "password": "5ebe2294ecd0e0f08eab7690d2a6ee69"}},
        ),
    ]


def test_request_first_success_includes_response_body_forbidden_detail() -> None:
    client = _client(_response(403, b'{"message": "User is not authorized"}'))

    with pytest.raises(AssertionError, match="not authorized.*User is not authorized"):
        client.request_first_success("GET", ("/rest/v2/test",))


def test_request_first_success_summarizes_html_error_pages() -> None:
    client = _client(
        _response(
            403,
            b"<!doctype html><html><head><title>HTTP Status 403 &ndash; Forbidden</title></head></html>",
        )
    )

    with pytest.raises(AssertionError, match="not authorized.*HTTP Status 403 . Forbidden"):
        client.request_first_success("GET", ("/rest/v2/test",))


def test_application_settings_use_management_settings_path_first() -> None:
    client = _client(_response(200, b'{"settings": true}'))

    client.get_application_settings()

    assert isinstance(client.session, StaticSession)
    assert client.session.requests == [
        ("GET", "https://server.example.test/rest/v2/applications/settings/live", {}),
    ]


def test_rest_api_token_is_sent_to_management_rest_paths() -> None:
    client = _client(_response(200, b'{"applications": ["live"]}'))
    client.config = Config(
        server_url=client.config.server_url,
        user="",
        password="",
        rest_api_token="token-value",
    )

    client.applications()

    assert isinstance(client.session, StaticSession)
    assert client.session.requests == [
        (
            "GET",
            "https://server.example.test/rest/v2/applications",
            {"headers": {"Authorization": "Bearer token-value"}},
        ),
    ]


def test_rest_api_token_uses_application_rest_paths() -> None:
    client = _client(_response(200, b'{"streamId": "stream1"}'))
    client.config = Config(
        server_url=client.config.server_url,
        user="",
        password="",
        rest_api_token="Bearer already-prefixed",
    )

    client.create_broadcast("stream1")

    assert isinstance(client.session, StaticSession)
    assert client.session.requests == [
        (
            "POST",
            "https://server.example.test/live/rest/v2/broadcasts/create",
            {"headers": {"Authorization": "Bearer already-prefixed"}, "json": {"streamId": "stream1"}},
        ),
    ]


def test_application_settings_use_application_rest_paths_first_when_token_is_configured() -> None:
    client = _client(_response(200, b'{"settings": true}'))
    client.config = Config(
        server_url=client.config.server_url,
        user="",
        password="",
        rest_api_token="token-value",
    )

    client.get_application_settings()

    assert isinstance(client.session, StaticSession)
    assert client.session.requests == [
        (
            "GET",
            "https://server.example.test/live/rest/v2/app-settings",
            {"headers": {"Authorization": "Bearer token-value"}},
        ),
    ]


def test_application_settings_update_uses_management_settings_post_first() -> None:
    client = _client(_response(200, b'{"success": true}'))

    client.set_application_settings({"settings": True})

    assert isinstance(client.session, StaticSession)
    assert client.session.requests == [
        ("POST", "https://server.example.test/rest/v2/applications/settings/live", {"json": {"settings": True}}),
    ]


def test_broadcast_create_uses_management_proxy_request_path() -> None:
    client = _client(_response(200, b'{"streamId": "stream1"}'))

    client.create_broadcast("stream1")

    assert isinstance(client.session, StaticSession)
    assert client.session.requests == [
        ("POST", "https://server.example.test/rest/v2/request?_path=live/rest/v2/broadcasts/create", {"json": {"streamId": "stream1"}}),
    ]


def test_broadcast_create_can_target_specific_application() -> None:
    client = _client(_response(200, b'{"streamId": "stream1"}'))

    client.create_broadcast("stream1", application="LiveApp")

    assert isinstance(client.session, StaticSession)
    assert client.session.requests == [
        ("POST", "https://server.example.test/rest/v2/request?_path=LiveApp/rest/v2/broadcasts/create", {"json": {"streamId": "stream1"}}),
    ]


def test_get_broadcast_can_target_specific_application() -> None:
    client = _client(_response(200, b'{"streamId": "stream1"}'))

    client.get_broadcast("stream1", application="LiveApp")

    assert isinstance(client.session, StaticSession)
    assert client.session.requests == [
        ("GET", "https://server.example.test/rest/v2/request?_path=LiveApp/rest/v2/broadcasts/stream1", {}),
    ]


def test_add_rtmp_endpoint_uses_endpointurl_payload_field() -> None:
    client = _client(_response(200, b'{"success": true}'))

    client.add_rtmp_endpoint("stream1", "rtmp://remote-endpoint/live/test")

    assert isinstance(client.session, StaticSession)
    assert client.session.requests == [
        (
            "POST",
            "https://server.example.test/rest/v2/request?_path=live/rest/v2/broadcasts/stream1/rtmp-endpoint",
            {"json": {"rtmpUrl": "rtmp://remote-endpoint/live/test", "endpointUrl": "rtmp://remote-endpoint/live/test"}},
        ),
    ]


def test_add_rtmp_endpoint_can_target_specific_application() -> None:
    client = _client(_response(200, b'{"success": true}'))

    client.add_rtmp_endpoint("stream1", "rtmp://server.example.test/LiveApp/stream1_rtmp_endpoint", application="LiveApp")

    assert isinstance(client.session, StaticSession)
    assert client.session.requests == [
        (
            "POST",
            "https://server.example.test/rest/v2/request?_path=LiveApp/rest/v2/broadcasts/stream1/rtmp-endpoint",
            {"json": {"rtmpUrl": "rtmp://server.example.test/LiveApp/stream1_rtmp_endpoint", "endpointUrl": "rtmp://server.example.test/LiveApp/stream1_rtmp_endpoint"}},
        ),
    ]
