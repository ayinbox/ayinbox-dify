"""A mocked HTTP layer that serves the AY Inbox fixtures. No test touches the network."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT))

from ayinbox_api import runner  # noqa: E402
from ayinbox_api.client import AyInboxClient  # noqa: E402

TEST_KEY = "aybox_" + "t" * 43
SUCCESS_HEADERS = json.loads((FIXTURES / "errors" / "index.json").read_text())["default_success_headers"]
ERROR_INDEX = json.loads((FIXTURES / "errors" / "index.json").read_text())["errors"]


def fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


def make_response(status: int, body: Any = None, headers: dict[str, str] | None = None) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    if body is None:
        response._content = b""
    elif isinstance(body, (bytes, str)):
        response._content = body.encode() if isinstance(body, str) else body
    else:
        response._content = json.dumps(body).encode()
    response.headers.update(headers if headers is not None else SUCCESS_HEADERS)
    return response


def error_response(name: str) -> requests.Response:
    meta = ERROR_INDEX[f"errors/{name}"]
    return make_response(meta["status"], fixture(f"errors/{name}"), meta["headers"])


class FakeHTTP:
    """Records each call and answers from a queue per (METHOD, path)."""

    def __init__(self) -> None:
        self.routes: dict[tuple[str, str], list[Any]] = {}
        self.calls: list[dict[str, Any]] = []

    def add(self, method: str, path: str, *responses: Any) -> FakeHTTP:
        self.routes.setdefault((method.upper(), path), []).extend(responses)
        return self

    def json(self, method: str, path: str, body: Any, status: int = 200) -> FakeHTTP:
        return self.add(method, path, make_response(status, body))

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        path = urlsplit(url).path
        self.calls.append({"method": method, "url": url, "path": path, **kwargs})
        queue = self.routes.get((method, path))
        if not queue:
            raise AssertionError(f"unexpected request {method} {path}")
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        return item

    def last(self) -> dict[str, Any]:
        return self.calls[-1]


@pytest.fixture
def http() -> FakeHTTP:
    return FakeHTTP()


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def client(http: FakeHTTP, sleeps: list[float]) -> AyInboxClient:
    return AyInboxClient(TEST_KEY, http=http, sleep=sleeps.append)


@pytest.fixture
def patched_factory(http: FakeHTTP, sleeps: list[float], monkeypatch: pytest.MonkeyPatch) -> FakeHTTP:
    monkeypatch.setattr(
        runner,
        "client_factory",
        lambda creds: AyInboxClient(str(creds.get("api_key") or ""), http=http, sleep=sleeps.append),
    )
    return http
