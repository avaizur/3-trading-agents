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
from urllib.parse import unquote, urlencode
from urllib.request import Request, urlopen


AUTHORIZATION_URL = "https://auth.ebay.com/oauth2/authorize"
TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
RUNAME = "Avais_Ahmad-AvaisAhm-Xorwia-idfjw"
SCOPES = (
    "https://api.ebay.com/oauth/api_scope",
    "https://api.ebay.com/oauth/api_scope/sell.inventory",
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
        "code": unquote(authorization_code),
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


def load_saved_tokens(path: Path | None = None) -> dict[str, Any]:
    """Load the private OAuth token file without logging token values."""
    source = (path or default_token_path()).expanduser()
    if not source.exists():
        raise OAuthError(f"Saved eBay OAuth token file not found: {source}")

    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OAuthError("Unable to read saved eBay OAuth tokens") from exc

    if not isinstance(payload, dict):
        raise OAuthError("Saved eBay OAuth token file is invalid")

    return payload


def refresh_access_token(
    refresh_token: str,
    client_id: str,
    client_secret: str,
    *,
    scope: str | None = None,
    transport: TokenTransport | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Mint a new User access token from an existing refresh token."""
    if not refresh_token or not client_id or not client_secret:
        raise ValueError("Refresh token, Client ID, and Client Secret are required")

    credentials = base64.b64encode(
        f"{client_id}:{client_secret}".encode("utf-8")
    ).decode("ascii")

    headers = {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }

    fields = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }

    # Scope is optional for eBay refresh. If present in the saved
    # consent token, preserve that same scope set.
    if scope:
        fields["scope"] = scope

    body = urlencode(fields).encode("ascii")

    payload = (transport or _post_token)(
        TOKEN_URL,
        body,
        headers,
        timeout,
    )

    if not isinstance(payload.get("access_token"), str):
        raise OAuthError("eBay token refresh did not return an access token")

    return dict(payload)


def refresh_saved_access_token(
    client_id: str,
    client_secret: str,
    *,
    path: Path | None = None,
    transport: TokenTransport | None = None,
    timeout: float = 15.0,
) -> Path:
    """
    Refresh the saved eBay User access token while preserving the
    long-lived refresh token if eBay does not return a replacement.
    """
    destination = (path or default_token_path()).expanduser()
    saved = load_saved_tokens(destination)

    refresh_token = saved.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise OAuthError("Saved eBay OAuth data does not contain a refresh token")

    scope = saved.get("scope")
    if not isinstance(scope, str):
        scope = None

    refreshed = refresh_access_token(
        refresh_token,
        client_id,
        client_secret,
        scope=scope,
        transport=transport,
        timeout=timeout,
    )

    merged = dict(saved)

    for key, value in refreshed.items():
        # A refresh normally returns a new access token, not a new
        # refresh token. Never overwrite a good refresh token with N/A.
        if key == "refresh_token" and (
            not isinstance(value, str)
            or not value.strip()
            or value.strip().upper() == "N/A"
        ):
            continue
        merged[key] = value

    store_tokens_securely(merged, destination)
    return destination
