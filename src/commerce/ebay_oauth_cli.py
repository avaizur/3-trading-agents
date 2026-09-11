"""Authorize an eBay seller against Production without echoing secret values."""

from __future__ import annotations

import argparse
import getpass
import os
import sys

from src.commerce.ebay_oauth import (
    OAuthError,
    build_authorization_url,
    exchange_authorization_code,
    store_tokens_securely,
)


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise OAuthError(f"{name} environment variable is required")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            "Set EBAY_CLIENT_ID and, for exchange, EBAY_CLIENT_SECRET. "
            "The authorization code is read from EBAY_AUTHORIZATION_CODE or a no-echo prompt. "
            "Tokens are stored in a private mode-0600 user config file."
        ),
    )
    parser.add_argument("command", choices=("authorize", "exchange"))
    args = parser.parse_args(argv)

    try:
        client_id = _required_env("EBAY_CLIENT_ID")
        if args.command == "authorize":
            print(build_authorization_url(client_id))
            return 0

        client_secret = _required_env("EBAY_CLIENT_SECRET")
        code = os.environ.get("EBAY_AUTHORIZATION_CODE") or getpass.getpass(
            "Paste the eBay authorization code (input hidden): "
        )
        if not code:
            raise OAuthError("An authorization code is required")
        payload = exchange_authorization_code(code, client_id, client_secret)
        destination = store_tokens_securely(payload)
        print(f"eBay Production tokens stored securely at {destination}")
        return 0
    except (OAuthError, ValueError) as exc:
        print(f"OAuth operation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
