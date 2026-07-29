# Remote MCP doorway

Agent-note remains skill-first. The optional remote doorway exists only for MCP
clients that cannot run the local skill, such as Claude on a phone:

```text
Claude mobile
  -> Anthropic's MCP proxy
  -> HTTPS + OAuth
  -> secure tunnel
  -> 127.0.0.1:8765/mcp on the Mac
  -> existing Agent-note service
  -> ~/.notes/
```

The remote doorway exposes the same six deterministic operations as the local
CLI: create, import, search, recent, tags, and guarded read. It does not expose
the shell, arbitrary filesystem access, or a general command runner.

## Requirements

- Install the optional remote dependencies with `uv sync --extra remote`.
- Configure an OAuth 2.1 / OIDC provider that issues JWT access tokens.
- Restrict that provider to the one identity allowed to use this Agent-note.
- Configure a stable HTTPS tunnel to the loopback listener.
- Keep the Mac awake and online while remote access is needed.

Never publish this server without OAuth. A tunnel supplies HTTPS reachability;
it does not replace authorization.

## Configuration

Set these outside the repository. Do not commit their values:

```text
AGENT_NOTE_MCP_PUBLIC_URL=https://notes.example.com/mcp
AGENT_NOTE_MCP_ISSUER_URL=https://your-issuer.example.com/
AGENT_NOTE_MCP_JWKS_URL=https://your-issuer.example.com/.well-known/jwks.json
AGENT_NOTE_MCP_AUDIENCE=https://notes.example.com/mcp
AGENT_NOTE_MCP_ALLOWED_SUBJECT=the-one-approved-user-id
AGENT_NOTE_MCP_REQUIRED_SCOPE=agent-note
```

Optional local listener settings:

```text
AGENT_NOTE_MCP_HOST=127.0.0.1
AGENT_NOTE_MCP_PORT=8765
```

The server rejects a non-loopback host and any public or identity URL that does
not use HTTPS. It will not start when a required setting is missing.

Validate configuration without opening a port:

```bash
uv run --extra remote agent-note-mcp --check
```

Start the loopback-only server:

```bash
uv run --extra remote agent-note-mcp
```

The server uses MCP 2026-07-28 stateless Streamable HTTP at `/mcp`.

## Connect Claude

Claude's documented OAuth callback is:

```text
https://claude.ai/api/mcp/auth_callback
```

Also allow its announced future callback:

```text
https://claude.com/api/mcp/auth_callback
```

After the OAuth provider and HTTPS tunnel are working:

1. Open Claude and go to **Customize -> Connectors**.
2. Choose **Add custom connector**.
3. Enter the public `/mcp` URL.
4. If the provider does not support dynamic client registration, enter its
   configured OAuth client ID and secret under advanced settings.
5. Complete the one-time login and consent flow.
6. Enable Agent-note in a conversation from **+ -> Connectors**.

The same remote connector is then available in Claude mobile when signed into
the same Claude account.

## Safe rollout and shutdown

1. Test search, recent, tags, and guarded read first.
2. Verify an unauthenticated request returns HTTP 401.
3. Verify another identity is rejected.
4. Test create with a disposable note.
5. Test full conversation import only after create succeeds.

To disable remote access immediately, stop the HTTPS tunnel. Revoking the OAuth
application or the user's grant provides a second kill switch. Local skill and
CLI use continue to work when the remote doorway is disabled.
