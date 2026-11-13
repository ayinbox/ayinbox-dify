"""Typed errors built from the AY Inbox error envelope."""

from __future__ import annotations

import math
import re
from typing import Any

DEFAULT_CODES = {
    400: "bad_request",
    401: "unauthorized",
    402: "insufficient_credits",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "unprocessable",
    429: "rate_limit_exceeded",
    500: "internal_error",
    501: "not_implemented",
    503: "service_unavailable",
}
_CODE_RE = re.compile(r"^[a-z0-9_]+$")


class AyInboxError(Exception):
    """Base error. ``code`` is the API's stable machine key; branch on it, not on the message."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: str | None = None,
        reason: str | None = None,
        request_id: str | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.reason = reason
        self.request_id = request_id
        self.retry_after = retry_after

    def describe(self) -> str:
        parts = ["AY Inbox API error"]
        if self.status is not None:
            parts.append(str(self.status))
        head = " ".join(parts)
        if self.code:
            head += f" ({self.code})"
        text = f"{head}: {self.message}"
        if self.retry_after is not None:
            text += f" Retry after {self.retry_after:g} seconds."
        if self.request_id:
            text += f" Request id: {self.request_id}."
        return text

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "code": self.code,
            "reason": self.reason,
            "message": self.message,
            "request_id": self.request_id,
            "retry_after": self.retry_after,
        }


class BadRequestError(AyInboxError):
    pass


class AuthenticationError(AyInboxError):
    pass


class PaymentRequiredError(AyInboxError):
    pass


class PermissionDeniedError(AyInboxError):
    pass


class NotFoundError(AyInboxError):
    pass


class ConflictError(AyInboxError):
    pass


class UnprocessableError(AyInboxError):
    pass


class RateLimitError(AyInboxError):
    pass


class InternalServerError(AyInboxError):
    pass


class ServiceUnavailableError(AyInboxError):
    pass


class AyInboxConnectionError(AyInboxError):
    pass


_BY_STATUS: dict[int, type[AyInboxError]] = {
    400: BadRequestError,
    401: AuthenticationError,
    402: PaymentRequiredError,
    403: PermissionDeniedError,
    404: NotFoundError,
    409: ConflictError,
    422: UnprocessableError,
    429: RateLimitError,
    503: ServiceUnavailableError,
}


def error_from_response(response: Any) -> AyInboxError:
    status = int(response.status_code)
    headers = response.headers or {}
    try:
        body = response.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        body = {}

    code = body.get("code")
    if not code:
        raw = body.get("error")
        code = raw if isinstance(raw, str) and _CODE_RE.match(raw) else DEFAULT_CODES.get(status, "http_error")

    message = body.get("message")
    if not isinstance(message, str) or not message:
        message = (getattr(response, "text", "") or "").strip()[:300] or f"HTTP {status}"

    request_id = body.get("request_id") or headers.get("X-Request-Id")
    cls = _BY_STATUS.get(status) or (InternalServerError if status >= 500 else AyInboxError)
    return cls(
        message,
        status=status,
        code=code,
        reason=body.get("reason"),
        request_id=request_id,
        retry_after=_retry_after(headers, body),
    )


def _retry_after(headers: Any, body: dict[str, Any]) -> float | None:
    header = headers.get("Retry-After")
    if header is not None:
        try:
            return max(0.0, float(header))
        except ValueError:
            pass
    if isinstance(body.get("retry_after"), (int, float)):
        return max(0.0, float(body["retry_after"]))
    if isinstance(body.get("retry_after_ms"), (int, float)):
        return float(math.ceil(body["retry_after_ms"] / 1000))
    return None
