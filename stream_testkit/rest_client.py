from __future__ import annotations

import html
import hashlib
import logging
import re
from typing import Any, Iterable
from urllib.parse import quote

import requests

from .config import TestConfig

logger = logging.getLogger(__name__)


def _cookie_names(cookie_header: str | None) -> str:
    if not cookie_header:
        return "none"
    names = []
    for cookie in cookie_header.split(";"):
        name = cookie.strip().split("=", 1)[0]
        if name:
            names.append(name)
    return ", ".join(names) if names else "none"


def _stored_cookie_summary(cookie_jar: requests.cookies.RequestsCookieJar) -> str:
    cookies = [
        f"{cookie.name}(domain={cookie.domain or 'default'}, path={cookie.path})"
        for cookie in cookie_jar
    ]
    return ", ".join(cookies) if cookies else "none"


class ServerClient:
    def __init__(self, config: TestConfig) -> None:
        self.config = config
        self.session = requests.Session()
        self.session.verify = config.verify_tls

    def _url(self, path: str) -> str:
        return f"{self.config.normalized_server_url}{path}"

    def _app_request_path(self, app_path: str) -> str:
        app_path = app_path.lstrip("/")
        return f"/rest/v2/request?_path={quote(app_path, safe='/')}"

    def _app_rest_path(self, app: str, rest_path: str) -> str:
        return f"/{app}/rest/v2/{rest_path.lstrip('/')}"

    def _app_name(self, application: str | None = None) -> str:
        return application or self.config.application

    def _has_panel_credentials(self) -> bool:
        return bool(self.config.user and self.config.password)

    def _app_rest_candidates(self, app: str, *rest_paths: str) -> tuple[str, ...]:
        if self.config.rest_api_token:
            return tuple(self._app_rest_path(app, rest_path) for rest_path in rest_paths)
        return tuple(self._app_request_path(f"{app}/rest/v2/{rest_path.lstrip('/')}") for rest_path in rest_paths)

    @staticmethod
    def _is_rest_path(path: str) -> bool:
        return path.startswith("/rest/") or bool(re.match(r"^/[^/]+/rest/", path))

    def _headers(self, path: str, kwargs: dict[str, Any]) -> dict[str, str] | None:
        headers = dict(kwargs.pop("headers", {}) or {})
        if self.config.rest_api_token and self._is_rest_path(path) and path != "/rest/v2/users/authenticate":
            token = self.config.rest_api_token
            headers.setdefault("Authorization", token if token.lower().startswith("bearer ") else f"Bearer {token}")
        return headers or None

    def request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        logger.info("REST %s %s", method, path)
        headers = self._headers(path, kwargs)
        if headers:
            kwargs["headers"] = headers
        url = self._url(path)
        try:
            response = self.session.request(method, url, timeout=30, **kwargs)
        except requests.RequestException as exc:
            raise AssertionError(self._request_exception_message(method, path, url, exc)) from exc
        request = getattr(response, "request", None)
        request_headers = getattr(request, "headers", {}) if request is not None else {}
        logger.info("REST %s %s sent cookies: %s", method, path, _cookie_names(request_headers.get("Cookie")))
        try:
            response.raise_for_status()
        except requests.HTTPError:
            logger.warning("REST %s %s -> HTTP %s%s", method, path, response.status_code, self._failure_detail(response))
            raise
        logger.info("REST %s %s -> HTTP %s", method, path, response.status_code)
        return response

    def _request_exception_message(
        self, method: str, path: str, url: str, exc: requests.RequestException
    ) -> str:
        message = (
            f"REST {method} {path} failed against {url}: {exc}. "
            f"Check that the server is running and that --server-url points to the web panel base URL."
        )
        if self.config.server_url.startswith("http://localhost:5080"):
            message += " This suite's README examples use a panel URL like https://SERVER_HOST:5443."
        return message

    @staticmethod
    def _failure_detail(response: requests.Response | None) -> str:
        if response is None or not response.text:
            return ""
        detail = response.text.strip()
        if detail.lstrip().lower().startswith(("<!doctype html", "<html")):
            title = re.search(r"<title[^>]*>(.*?)</title>", detail, flags=re.IGNORECASE | re.DOTALL)
            if title:
                detail = title.group(1)
            else:
                detail = re.sub(r"<[^>]+>", " ", detail)
        detail = html.unescape(detail)
        detail = re.sub(r"\s+", " ", detail).strip()
        if len(detail) > 200:
            detail = f"{detail[:197]}..."
        return f": {detail}"

    def request_first_success(self, method: str, paths: Iterable[str], **kwargs: Any) -> requests.Response:
        failures: list[str] = []
        statuses: list[int] = []
        for path in paths:
            try:
                return self.request(method, path, **kwargs)
            except requests.HTTPError as exc:
                response = exc.response
                status = response.status_code if response is not None else "unknown"
                if isinstance(status, int):
                    statuses.append(status)
                failures.append(f"{path} -> HTTP {status}{self._failure_detail(response)}")
            except requests.RequestException as exc:
                failures.append(f"{path} -> {exc}")
        if statuses and all(status == 403 for status in statuses):
            raise AssertionError(
                "All candidate REST paths returned HTTP 403 Forbidden. "
                "Authentication succeeded, but this user/session is not authorized for the requested endpoint(s). "
                "Check the user role, application permissions, and REST security settings. "
                "Tried: "
                + "; ".join(failures)
            )
        raise AssertionError("No candidate REST path succeeded: " + "; ".join(failures))

    def request_first_success_candidate(
        self, candidates: Iterable[tuple[str, str]], **kwargs: Any
    ) -> requests.Response:
        failures: list[str] = []
        statuses: list[int] = []
        for method, path in candidates:
            try:
                return self.request(method, path, **kwargs)
            except requests.HTTPError as exc:
                response = exc.response
                status = response.status_code if response is not None else "unknown"
                if isinstance(status, int):
                    statuses.append(status)
                failures.append(f"{method} {path} -> HTTP {status}{self._failure_detail(response)}")
            except requests.RequestException as exc:
                failures.append(f"{method} {path} -> {exc}")
        if statuses and all(status == 403 for status in statuses):
            raise AssertionError(
                "All candidate REST paths returned HTTP 403 Forbidden. "
                "Authentication succeeded, but this user/session is not authorized for the requested endpoint(s). "
                "Check the user role, application permissions, and REST security settings. "
                "Tried: "
                + "; ".join(failures)
            )
        raise AssertionError("No candidate REST path succeeded: " + "; ".join(failures))

    def authenticate(self) -> dict[str, Any]:
        if self.config.rest_api_token and not self._has_panel_credentials():
            logger.info("Skipping cookie authentication because TESTKIT_REST_API_TOKEN is configured and no panel credentials were provided")
            return {"success": True, "auth": "token"}
        password_hash = hashlib.md5(self.config.password.encode("utf-8")).hexdigest()
        response = self.request(
            "POST",
            "/rest/v2/users/authenticate",
            json={"email": self.config.user, "password": password_hash},
        )
        data = response.json() if response.content else {}
        if isinstance(data, dict) and data.get("success") is False:
            message = data.get("message") or data.get("error") or "authentication was rejected"
            if len(self.config.password) == 32 and all(char in "0123456789abcdefABCDEF" for char in self.config.password):
                message = f"{message}. Pass the raw panel password to --password, not an MD5 hash"
            raise AssertionError(f"Server authentication failed for {self.config.user}: {message}")
        logger.info(
            "Authentication stored cookies: %s",
            _stored_cookie_summary(getattr(self.session, "cookies", requests.cookies.RequestsCookieJar())),
        )
        return data

    def applications(self) -> list[str]:
        response = self.request("GET", "/rest/v2/applications")
        data = response.json()
        return data.get("applications", data if isinstance(data, list) else [])

    def system_resources(self) -> dict[str, Any]:
        return self.request("GET", "/rest/v2/system-resources").json()

    def system_settings(self) -> dict[str, Any]:
        response = self.request_first_success(
            "GET",
            ("/rest/v2/system-settings", "/rest/v2/server-settings", "/rest/v2/settings"),
        )
        return response.json()

    def get_application_settings(self) -> dict[str, Any]:
        app = self.config.application
        app_paths = (
            f"/{app}/rest/v2/app-settings",
            f"/{app}/rest/v2/settings",
            f"/rest/v2/applications/settings/{app}",
        ) if self.config.rest_api_token else (
            f"/rest/v2/applications/settings/{app}",
            f"/{app}/rest/v2/app-settings",
            f"/{app}/rest/v2/settings",
        )
        response = self.request_first_success(
            "GET",
            app_paths,
        )
        return response.json()

    def set_application_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        app = self.config.application
        candidates = (
            ("PUT", f"/{app}/rest/v2/app-settings"),
            ("PUT", f"/{app}/rest/v2/settings"),
            ("POST", f"/rest/v2/applications/settings/{app}"),
        ) if self.config.rest_api_token else (
            ("POST", f"/rest/v2/applications/settings/{app}"),
            ("PUT", f"/{app}/rest/v2/app-settings"),
            ("PUT", f"/{app}/rest/v2/settings"),
        )
        response = self.request_first_success_candidate(
            candidates,
            json=settings,
        )
        return response.json() if response.content else {"success": True}

    def create_broadcast(self, stream_id: str, name: str | None = None, *, application: str | None = None) -> dict[str, Any]:
        app = self._app_name(application)
        payload = {"streamId": stream_id}
        if name:
            payload["name"] = name
        response = self.request("POST", self._app_rest_candidates(app, "broadcasts/create")[0], json=payload)
        return response.json()

    def get_broadcast(self, stream_id: str, *, application: str | None = None) -> dict[str, Any]:
        app = self._app_name(application)
        return self.request("GET", self._app_rest_candidates(app, f"broadcasts/{stream_id}")[0]).json()

    def broadcast_statistics(self, stream_id: str) -> dict[str, Any]:
        app = self.config.application
        return self.request(
            "GET",
            self._app_rest_candidates(app, f"broadcasts/{stream_id}/broadcast-statistics")[0],
        ).json()

    def add_rtmp_endpoint(self, stream_id: str, endpoint_url: str, *, application: str | None = None) -> dict[str, Any]:
        app = self._app_name(application)
        rtmp_paths = self._app_rest_candidates(
            app,
            f"broadcasts/{stream_id}/rtmp-endpoint",
            f"broadcasts/{stream_id}/rtmp-endpoints",
        )
        response = self.request_first_success_candidate(
            (
                ("POST", rtmp_paths[0]),
                ("POST", rtmp_paths[1]),
            ),
            json={"rtmpUrl": endpoint_url, "endpointUrl": endpoint_url},
        )
        return response.json() if response.content else {"success": True}
