import asyncio
import time

import httpx
import jwt
import pytest

from agent_note import remote_server


def settings(**overrides):
    values = {
        "public_url": "https://notes.example.com/mcp",
        "issuer_url": "https://auth.example.com/",
        "jwks_url": "https://auth.example.com/.well-known/jwks.json",
        "audience": "https://notes.example.com/mcp",
        "allowed_subject": "jack",
    }
    values.update(overrides)
    return remote_server.RemoteSettings(**values)


def test_configuration_requires_every_secret(monkeypatch):
    for name in (
        "PUBLIC_URL",
        "ISSUER_URL",
        "JWKS_URL",
        "AUDIENCE",
        "ALLOWED_SUBJECT",
    ):
        monkeypatch.delenv(f"AGENT_NOTE_MCP_{name}", raising=False)

    with pytest.raises(remote_server.ConfigurationError, match="remains disabled"):
        remote_server.RemoteSettings.from_environment()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("public_url", "http://notes.example.com/mcp", "must use https"),
        ("public_url", "https://notes.example.com/api", "must end with /mcp"),
        ("host", "0.0.0.0", "must bind to loopback"),
    ],
)
def test_configuration_rejects_unsafe_network_settings(field, value, message):
    with pytest.raises(remote_server.ConfigurationError, match=message):
        settings(**{field: value}).validate()


def test_transport_security_allows_only_configured_public_host():
    security = remote_server._transport_security(settings())

    assert security.enable_dns_rebinding_protection is True
    assert "notes.example.com" in security.allowed_hosts
    assert "127.0.0.1:*" in security.allowed_hosts
    assert "*" not in security.allowed_hosts


class FakeSigningKey:
    key = "test-key"


class FakeJwks:
    def get_signing_key_from_jwt(self, token):
        assert token == "signed-token"
        return FakeSigningKey()


def test_verifier_accepts_only_allowed_user_and_scope(monkeypatch):
    verifier = remote_server.OidcJwtVerifier(settings())
    verifier._jwks = FakeJwks()
    claims = {
        "sub": "jack",
        "scope": "openid agent-note",
        "exp": int(time.time()) + 600,
        "iat": int(time.time()),
        "azp": "claude",
    }
    monkeypatch.setattr(jwt, "decode", lambda *args, **kwargs: claims)

    result = asyncio.run(verifier.verify_token("signed-token"))

    assert result is not None
    assert result.subject == "jack"
    assert result.scopes == ["openid", "agent-note"]


def test_verifier_rejects_other_users(monkeypatch):
    verifier = remote_server.OidcJwtVerifier(settings())
    verifier._jwks = FakeJwks()
    monkeypatch.setattr(
        jwt,
        "decode",
        lambda *args, **kwargs: {
            "sub": "someone-else",
            "scope": "agent-note",
            "exp": int(time.time()) + 600,
            "iat": int(time.time()),
        },
    )

    assert asyncio.run(verifier.verify_token("signed-token")) is None


class AllowNothingVerifier:
    async def verify_token(self, token):
        return None


def test_remote_server_exposes_only_existing_six_operations():
    server = remote_server.create_remote_server(
        settings(), token_verifier=AllowNothingVerifier()
    )

    tools = asyncio.run(server.list_tools())

    assert [tool.name for tool in tools] == [
        "create_note",
        "import_conversation",
        "search_notes",
        "list_recent_notes",
        "list_tags",
        "read_note",
    ]


def test_remote_http_endpoint_is_locked_without_oauth_token():
    server = remote_server.create_remote_server(
        settings(), token_verifier=AllowNothingVerifier()
    )
    app = server.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
    )

    async def request():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="https://notes.example.com",
        ) as client:
            return await client.post(
                "/mcp",
                headers={
                    "MCP-Protocol-Version": "2026-07-28",
                    "Mcp-Method": "server/discover",
                    "Content-Type": "application/json",
                },
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "server/discover",
                    "params": {},
                },
            )

    response = asyncio.run(request())

    assert response.status_code == 401
    assert "resource_metadata=" in response.headers["www-authenticate"]


def test_remote_create_delegates_to_existing_service(monkeypatch):
    server = remote_server.create_remote_server(
        settings(), token_verifier=AllowNothingVerifier()
    )
    monkeypatch.setattr(
        remote_server.service,
        "create_note",
        lambda content, tags=None, title=None: {
            "content": content,
            "tags": tags,
            "title": title,
        },
    )

    result = asyncio.run(
        server.call_tool(
            "create_note",
            {"content": "Remember this", "title": "Test", "tags": ["remote"]},
        )
    )

    assert result.structured_content == {
        "content": "Remember this",
        "tags": ["remote"],
        "title": "Test",
    }
