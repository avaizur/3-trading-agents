"""Minimal eBay Production OAuth support for seller authorization.

Credentials and token values are deliberately kept out of messages and
exceptions.  The CLI in :mod:`src.commerce.ebay_oauth_cli` is the intended
interactive entry point.
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


AUTHORIZATION_URL = "https://auth.ebay.com/oauth2/authorize"
TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
RUNAME = "Avais_Ahmad-AvaisAhm-Xorwia-idfjw"
SCOPES = (
    "https://api.ebay.com/oauth/api_scope",
    "https://api.ebay.com/oauth/api_scope/sell.inventory.readonly",
    "https://api.ebay.com/oauth/api_scope/sell.account.readonly",
)

TokenTransport = Callable[[str, bytes, Mapping[str, str], float], Mapping[str, Any]]


class OAuthError(RuntimeError):
    """An OAuth operation failed without exposing the server response body."""


def build_authorization_url(client_id: str) -> str:
    """Build the Production consent URL for the fixed RuName and scopes."""
    if not client_id or not client_id.strip():
        raise ValueError("Client ID is required")
    query = urlencode({
        "client_id": client_id.strip(),
        "redirect_uri": RUNAME,
        "response_type": "code",
        "scope": " ".join(SCOPES),
    })
    return f"{AUTHORIZATION_URL}?{query}"


def _post_token(url: str, body: bytes, headers: Mapping[str, str], timeout: float) -> Mapping[str, Any]:
    request = Request(url, data=body, headers=dict(headers), method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed eBay host
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise OAuthError(f"eBay token exchange failed with HTTP status {exc.code}") from None
    except (URLError, TimeoutError):
        raise OAuthError("eBay token exchange could not reach the Production endpoint") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise OAuthError("eBay token exchange returned an invalid response") from None
    if not isinstance(payload, dict):
        raise OAuthError("eBay token exchange returned an invalid response")
    return payload


def exchange_authorization_code(
    authorization_code: str,
    client_id: str,
    client_secret: str,
    *,
    transport: TokenTransport | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Exchange a code without logging credentials or returning them in errors."""
    if not authorization_code or not client_id or not client_secret:
        raise ValueError("Authorization code, Client ID, and Client Secret are required")
    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    headers = {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    body = urlencode({
        "grant_type": "authorization_code",
        "code": authorization_code,
        "redirect_uri": RUNAME,
    }).encode("ascii")
    payload = (transport or _post_token)(TOKEN_URL, body, headers, timeout)
    if not isinstance(payload.get("access_token"), str):
        raise OAuthError("eBay token exchange did not return an access token")
    return dict(payload)


def default_token_path() -> Path:
    """Return a user-private config path, outside the repository by default."""
    config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(config_home).expanduser() if config_home else Path.home() / ".config"
    return base / "trading-agents" / "ebay-production-oauth.json"


def store_tokens_securely(token_payload: Mapping[str, Any], path: Path | None = None) -> Path:
    """Atomically store only OAuth token fields in a mode-0600 file."""
    destination = (path or default_token_path()).expanduser()
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(destination.parent, 0o700)
    allowed = {
        key: token_payload[key]
        for key in (
            "access_token", "refresh_token", "expires_in",
            "refresh_token_expires_in", "token_type", "scope",
        )
        if key in token_payload
    }
    if not isinstance(allowed.get("access_token"), str):
        raise ValueError("Token payload must contain an access token")

    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent,
            prefix=f".{destination.name}.", delete=False,
        ) as temporary:
            temporary_name = temporary.name
            os.chmod(temporary.name, 0o600)
            json.dump(allowed, temporary, separators=(",", ":"))
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, destination)
        os.chmod(destination, 0o600)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return destination
