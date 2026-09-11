import json
import os
from urllib.parse import parse_qs, urlparse

from src.commerce import ebay_oauth
from src.commerce.ebay_oauth_cli import main


def test_authorization_url_uses_production_runame_and_only_required_scopes():
    url = ebay_oauth.build_authorization_url("public-client-id")
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == ebay_oauth.AUTHORIZATION_URL
    assert query == {
        "client_id": ["public-client-id"],
        "redirect_uri": [ebay_oauth.RUNAME],
        "response_type": ["code"],
        "scope": [" ".join(ebay_oauth.SCOPES)],
    }


def test_exchange_posts_form_with_basic_auth_without_secret_in_result_metadata():
    calls = []

    def transport(url, body, headers, timeout):
        calls.append((url, body, headers, timeout))
        return {"access_token": "access-value", "refresh_token": "refresh-value", "expires_in": 7200}

    result = ebay_oauth.exchange_authorization_code(
        "code-value", "client-value", "secret-value", transport=transport
    )

    assert result["expires_in"] == 7200
    url, body, headers, timeout = calls[0]
    assert url == ebay_oauth.TOKEN_URL
    assert parse_qs(body.decode("ascii")) == {
        "grant_type": ["authorization_code"],
        "code": ["code-value"],
        "redirect_uri": [ebay_oauth.RUNAME],
    }
    assert headers["Authorization"].startswith("Basic ")
    assert "secret-value" not in headers["Authorization"]
    assert timeout == 15.0


def test_secure_store_is_private_and_keeps_only_token_fields(tmp_path):
    destination = tmp_path / "private" / "tokens.json"
    ebay_oauth.store_tokens_securely({
        "access_token": "access-value",
        "refresh_token": "refresh-value",
        "expires_in": 7200,
        "unexpected": "discard-me",
    }, destination)

    assert os.stat(destination).st_mode & 0o777 == 0o600
    assert os.stat(destination.parent).st_mode & 0o777 == 0o700
    stored = json.loads(destination.read_text(encoding="utf-8"))
    assert stored == {
        "access_token": "access-value",
        "refresh_token": "refresh-value",
        "expires_in": 7200,
    }


def test_authorize_cli_reads_client_id_from_env(monkeypatch, capsys):
    monkeypatch.setenv("EBAY_CLIENT_ID", "public-client-id")

    assert main(["authorize"]) == 0

    output = capsys.readouterr()
    assert "public-client-id" in output.out
    assert output.err == ""


def test_exchange_cli_never_echoes_secret_material(monkeypatch, tmp_path, capsys):
    secrets = ("secret-value", "code-value", "access-value", "refresh-value")
    monkeypatch.setenv("EBAY_CLIENT_ID", "public-client-id")
    monkeypatch.setenv("EBAY_CLIENT_SECRET", secrets[0])
    monkeypatch.setenv("EBAY_AUTHORIZATION_CODE", secrets[1])
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(
        "src.commerce.ebay_oauth_cli.exchange_authorization_code",
        lambda code, client_id, client_secret: {
            "access_token": secrets[2], "refresh_token": secrets[3]
        },
    )

    assert main(["exchange"]) == 0

    captured = capsys.readouterr()
    console = captured.out + captured.err
    assert not any(value in console for value in secrets)
    assert json.loads(ebay_oauth.default_token_path().read_text())["access_token"] == secrets[2]
