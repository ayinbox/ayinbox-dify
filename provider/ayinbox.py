from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from ayinbox_api import runner
from ayinbox_api.errors import AuthenticationError, AyInboxError

KEY_PREFIXES = ("aybox_", "ayat_")


class AyInboxProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        api_key = str(credentials.get("api_key") or "").strip()
        if not api_key.startswith(KEY_PREFIXES):
            raise ToolProviderCredentialValidationError(
                "An AY Inbox API key starts with aybox_ (or ayat_ for an OAuth token)."
            )
        try:
            runner.client_factory({"api_key": api_key}).request("GET", "/me")
        except AuthenticationError as err:
            raise ToolProviderCredentialValidationError(
                f"AY Inbox refused this key ({err.code}). Create a new key and paste it again."
            ) from None
        except AyInboxError as err:
            raise ToolProviderCredentialValidationError(err.describe()) from None
