"""HTTP client for the AY Inbox REST API, shared by every tool in this plugin."""

from __future__ import annotations

import math
import random
import re
import time
from collections.abc import Callable, Mapping
from typing import Any

import requests

from ayinbox_api.errors import (
    AyInboxConnectionError,
    AyInboxError,
    error_from_response,
)

VERSION = "0.1.0"
BASE_URL = "https://api.ayinbox.com/v1"
USER_AGENT = f"ayinbox-dify/{VERSION}"
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 2
RETRY_STATUSES = frozenset({429, 502, 503, 504})
# A tool call runs inside a Dify request with its own deadline, so long waits fail instead.
MAX_RETRY_AFTER_SECONDS = 30.0
BACKOFF_BASE = 0.5
BACKOFF_CAP = 8.0
IDEMPOTENCY_KEY_RE = re.compile(r"^[\x21-\x7e]{1,255}$")


class AyInboxClient:
    """Sends requests to the fixed hosted API with auth, retries and typed errors."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        http: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        api_key = (api_key or "").strip()
        if not api_key:
            raise ValueError("An AY Inbox API key is required.")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max(0, int(max_retries))
        self._http = http if http is not None else requests.Session()
        self._sleep = sleep

    def __repr__(self) -> str:
        return f"AyInboxClient(base_url={self._base_url!r}, api_key='***')"

    def request(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, Any] | None = None,
        body: Any = None,
        idempotency_key: str | None = None,
        read_only: bool = False,
    ) -> Any:
        """Send one call and return the decoded JSON body (None for an empty body).

        ``read_only`` marks a POST that only reads (contact search), which is safe to retry.
        """
        method = method.upper()
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        if idempotency_key:
            if not IDEMPOTENCY_KEY_RE.match(idempotency_key):
                raise ValueError("The idempotency key must be 1 to 255 visible ASCII characters.")
            headers["Idempotency-Key"] = idempotency_key

        params = _clean_query(query)
        url = self._base_url + "/" + path.lstrip("/")
        replay_safe = read_only or method in {"GET", "HEAD", "PUT", "DELETE"} or bool(idempotency_key)

        attempt = 0
        while True:
            try:
                response = self._http.request(
                    method,
                    url,
                    params=params or None,
                    json=body,
                    headers=headers,
                    timeout=self._timeout,
                    allow_redirects=False,
                )
            except (requests.ConnectionError, requests.Timeout) as err:
                if replay_safe and attempt < self._max_retries:
                    self._sleep(_backoff(attempt))
                    attempt += 1
                    continue
                raise AyInboxConnectionError(f"Could not reach the AY Inbox API ({type(err).__name__}).") from None

            status = response.status_code
            if 200 <= status < 300:
                return _decode(response)

            error = error_from_response(response)
            if self._should_retry(error, status, replay_safe, attempt):
                wait = error.retry_after if error.retry_after is not None else _backoff(attempt)
                self._sleep(wait)
                attempt += 1
                continue
            raise error

    def _should_retry(self, error: AyInboxError, status: int, replay_safe: bool, attempt: int) -> bool:
        if attempt >= self._max_retries or status not in RETRY_STATUSES:
            return False
        if error.code == "idempotency_outcome_unknown":
            return False
        if error.retry_after is not None and error.retry_after > MAX_RETRY_AFTER_SECONDS:
            return False
        # A 429 was refused before it ran, so even a keyless mutation may be sent again.
        return status == 429 or replay_safe


def _clean_query(query: Mapping[str, Any] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in (query or {}).items():
        if value is None or value == "":
            continue
        if isinstance(value, bool):
            out[key] = "true" if value else "false"
        else:
            out[key] = str(value)
    return out


def _decode(response: Any) -> Any:
    text = response.text
    if not text or not text.strip():
        return None
    try:
        return response.json()
    except ValueError:
        return text


def _backoff(attempt: int) -> float:
    return random.uniform(0, min(BACKOFF_CAP, BACKOFF_BASE * math.pow(2, attempt)))
