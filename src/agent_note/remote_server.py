"""Optional authenticated remote MCP doorway for Agent-note.

The skill and CLI remain Agent-note's primary interfaces. This module is a thin
HTTP adapter over the existing deterministic service and storage functions.
It deliberately refuses to start without a complete OAuth configuration.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from typing import Any

import jwt
from jwt import PyJWKClient
from mcp.server import MCPServer
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from pydantic import AnyHttpUrl

from agent_note import embeddings, notes_store, service

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_SCOPE = "agent-note"


class ConfigurationError(ValueError):
    """Remote server configuration is incomplete or unsafe."""


@dataclass(frozen=True)
class RemoteSettings:
    """Validated settings for one private remote Agent-note server."""

    public_url: str
    issuer_url: str
    jwks_url: str
    audience: str
    allowed_subject: str
    required_scope: str = DEFAULT_SCOPE
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT

    @classmethod
    def from_environment(cls) -> RemoteSettings:
        values = {
            "public_url": os.getenv("AGENT_NOTE_MCP_PUBLIC_URL", "").strip(),
            "issuer_url": os.getenv("AGENT_NOTE_MCP_ISSUER_URL", "").strip(),
            "jwks_url": os.getenv("AGENT_NOTE_MCP_JWKS_URL", "").strip(),
            "audience": os.getenv("AGENT_NOTE_MCP_AUDIENCE", "").strip(),
            "allowed_subject": os.getenv(
                "AGENT_NOTE_MCP_ALLOWED_SUBJECT", ""
            ).strip(),
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            rendered = ", ".join(
                f"AGENT_NOTE_MCP_{name.upper()}" for name in missing
            )
            raise ConfigurationError(
                f"remote MCP remains disabled; missing: {rendered}"
            )

        required_scope = os.getenv(
            "AGENT_NOTE_MCP_REQUIRED_SCOPE", DEFAULT_SCOPE
        ).strip()
        host = os.getenv("AGENT_NOTE_MCP_HOST", DEFAULT_HOST).strip()
        try:
            port = int(os.getenv("AGENT_NOTE_MCP_PORT", str(DEFAULT_PORT)))
        except ValueError as exc:
            raise ConfigurationError("AGENT_NOTE_MCP_PORT must be an integer") from exc

        settings = cls(
            **values,
            required_scope=required_scope,
            host=host,
            port=port,
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        for name in ("public_url", "issuer_url", "jwks_url"):
            value = getattr(self, name)
            parsed = AnyHttpUrl(value)
            if parsed.scheme != "https":
                raise ConfigurationError(f"{name} must use https")
        if not self.public_url.rstrip("/").endswith("/mcp"):
            raise ConfigurationError("public_url must end with /mcp")
        if self.host not in {"127.0.0.1", "::1", "localhost"}:
            raise ConfigurationError(
                "remote MCP must bind to loopback; use a secure tunnel for HTTPS"
            )
        if not 1 <= self.port <= 65535:
            raise ConfigurationError("port must be between 1 and 65535")
        if not self.required_scope:
            raise ConfigurationError("required_scope must not be empty")


def _scopes_from_claims(claims: dict[str, Any]) -> list[str]:
    raw = claims.get("scope", claims.get("scp", []))
    if isinstance(raw, str):
        return [item for item in raw.split() if item]
    if isinstance(raw, list) and all(isinstance(item, str) for item in raw):
        return raw
    return []


class OidcJwtVerifier(TokenVerifier):
    """Validate OAuth access tokens from one configured OIDC issuer."""

    def __init__(self, settings: RemoteSettings):
        self.settings = settings
        self._jwks = PyJWKClient(settings.jwks_url)

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            signing_key = self._jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "ES256"],
                audience=self.settings.audience,
                issuer=self.settings.issuer_url,
                options={"require": ["exp", "iat", "sub"]},
            )
        except jwt.PyJWTError:
            return None

        subject = str(claims.get("sub", ""))
        email = str(claims.get("email", ""))
        if self.settings.allowed_subject not in {subject, email}:
            return None

        scopes = _scopes_from_claims(claims)
        if self.settings.required_scope not in scopes:
            return None

        return AccessToken(
            token=token,
            client_id=str(claims.get("azp", claims.get("client_id", ""))),
            scopes=scopes,
            expires_at=int(claims["exp"]),
            resource=self.settings.public_url,
            subject=subject,
            claims=claims,
        )


def create_remote_server(
    settings: RemoteSettings,
    *,
    token_verifier: TokenVerifier | None = None,
) -> MCPServer:
    """Build the authenticated MCP adapter without starting a network listener."""
    settings.validate()
    server = MCPServer(
        name="Agent-note",
        description="Private, append-only notes stored on the owner's Mac.",
        instructions=(
            "Use Agent-note only when the user explicitly asks to save, import, "
            "or recall durable notes. Never save casual chat automatically. "
            "For a complete conversation import, preserve the raw transcript "
            "first, then follow the returned next_action."
        ),
        version="0.1.0",
        token_verifier=token_verifier or OidcJwtVerifier(settings),
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(settings.issuer_url),
            required_scopes=[settings.required_scope],
            resource_server_url=AnyHttpUrl(settings.public_url),
        ),
    )

    @server.tool()
    def create_note(
        content: str,
        title: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create one append-only note after the user explicitly asks to save it."""
        return service.create_note(content, tags=tags, title=title)

    @server.tool()
    def import_conversation(
        content: str,
        original_date: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        """Preserve one complete conversation and return its processing contract."""
        return service.import_conversation(
            content,
            original_date=original_date,
            title=title,
        )

    @server.tool()
    def search_notes(
        query: str,
        limit: int = 10,
        tags: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search normal notes by meaning, keywords, and optional tags."""
        return embeddings.search(query, limit=limit, tags=tags)

    @server.tool()
    def list_recent_notes(
        days: int = 7,
        tags: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """List recent normal notes, optionally filtered by tag."""
        return notes_store.list_recent(days=days, tags=tags)

    @server.tool()
    def list_tags() -> list[dict[str, Any]]:
        """List normalized note tags and their usage counts."""
        return notes_store.list_tags()

    @server.tool()
    def read_note(path: str) -> dict[str, str]:
        """Read one guarded Markdown note path returned by Agent-note."""
        return {"path": path, "content": notes_store.read_note(path)}

    return server


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-note-mcp",
        description="Run Agent-note's optional authenticated remote MCP doorway.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate configuration without opening a listener.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        settings = RemoteSettings.from_environment()
        server = create_remote_server(settings)
    except (ConfigurationError, ValueError) as exc:
        print(f"Agent-note remote MCP is disabled: {exc}")
        return 2

    if args.check:
        print("Agent-note remote MCP configuration is valid.")
        return 0

    server.run(
        transport="streamable-http",
        host=settings.host,
        port=settings.port,
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
