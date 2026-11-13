"""Glue between a Dify Tool instance and an operation."""

from __future__ import annotations

from collections.abc import Callable, Generator, Mapping
from typing import Any

from ayinbox_api.client import AyInboxClient
from ayinbox_api.errors import AyInboxError
from ayinbox_api.operations import OPERATIONS, describe_error
from ayinbox_api.params import InputError


class AyInboxToolError(Exception):
    """Raised to Dify so a workflow node fails and an agent sees the reason."""


def default_client(credentials: Mapping[str, Any]) -> AyInboxClient:
    return AyInboxClient(str(credentials.get("api_key") or ""))


# Tests replace this to serve fixtures instead of the network.
client_factory: Callable[[Mapping[str, Any]], AyInboxClient] = default_client


def run(tool: Any, name: str, tool_parameters: dict[str, Any]) -> Generator[Any, None, None]:
    op = OPERATIONS[name]
    try:
        client = client_factory(tool.runtime.credentials or {})
        result = op(client, dict(tool_parameters or {}))
    except InputError as err:
        raise AyInboxToolError(f"Invalid input: {err}") from None
    except AyInboxError as err:
        raise AyInboxToolError(describe_error(err, op)) from None
    except ValueError as err:
        raise AyInboxToolError(str(err)) from None
    yield tool.create_json_message(result.data)
    yield tool.create_text_message(result.summary)
