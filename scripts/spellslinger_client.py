"""A minimal client for the spellslinger MCP server (`docs/mcp-tools.md`),
speaking its streamable-HTTP wire protocol directly rather than through an
MCP SDK: JSON-RPC 2.0 over one POST endpoint, an `initialize` handshake that
hands back an `Mcp-Session-Id` header replayed on every later request, and
`tools/call` responses whose `content[].text` is the tool's own JSON
payload.

Ported from a throwaway probe script (`mcpc.py`) written while exploring the
`statistics_archetypes`/`statistics_decks` tools for
`scripts/fetch_metagame.py`; this is the same protocol, typed and split from
one-off exploration into a reusable client plus an injectable `Transport`
so callers (and tests) never have to hit the network to exercise their own
logic.
"""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Mapping
from typing import Any, Protocol

DEFAULT_URL = "https://mcp.szymonrichert.pl/mcp"
_PROTOCOL_VERSION = "2025-03-26"
_HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}


class MCPCallError(RuntimeError):
    """A `tools/call` did not come back with a usable result: a JSON-RPC
    `error`, a tool result flagged `isError`, a response with neither
    `result` nor `error` at all, or a body that was empty or not valid
    JSON. Raised rather than `call` returning `""` or `None` - a caller
    that only checks "was the list empty" (`response_items`, for one) must
    never mistake a broken call for zero real results."""

    def __init__(self, tool: str, arguments: Mapping[str, Any], reason: str) -> None:
        super().__init__(f"{tool}({dict(arguments)!r}): {reason}")
        self.tool = tool
        self.arguments = dict(arguments)


class Transport(Protocol):
    """What `SpellslingerClient` needs from whatever actually sends a
    `tools/call` request - real HTTP in production
    (`MCPTransport`), a scripted fake in tests."""

    def call(self, tool: str, **arguments: Any) -> Any: ...


class MCPTransport:
    """The real transport: one streamable-HTTP session against the
    spellslinger server. `call` returns the tool's own decoded JSON payload
    (a list or a dict, whatever the tool itself returns) - this class knows
    nothing about what any particular tool's payload looks like."""

    def __init__(self, url: str = DEFAULT_URL, *, timeout: float = 120.0) -> None:
        self._url = url
        self._timeout = timeout
        self._session_id: str | None = None
        self._next_id = 0
        self._post(
            {
                "jsonrpc": "2.0",
                "id": self._alloc_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": _PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "magic-cards-model-fetch-metagame", "version": "0"},
                },
            }
        )
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, notify=True)

    def _alloc_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def _post(self, body: Mapping[str, Any], *, notify: bool = False) -> dict[str, Any] | None:
        headers = dict(_HEADERS)
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        request = urllib.request.Request(
            self._url, json.dumps(body).encode(), headers=headers, method="POST"
        )
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            if self._session_id is None:
                self._session_id = response.headers.get("Mcp-Session-Id")
            raw = response.read().decode()
        if notify:
            return None
        stripped = raw.lstrip()
        if stripped.startswith("{"):
            return json.loads(stripped)
        for line in raw.splitlines():
            if line.startswith("data:"):
                return json.loads(line[len("data:") :])
        raise ValueError(f"no JSON-RPC payload in streamable response: {raw[:200]!r}")

    def call(self, tool: str, **arguments: Any) -> Any:
        response = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._alloc_id(),
                "method": "tools/call",
                "params": {"name": tool, "arguments": arguments},
            }
        )
        assert response is not None  # only the `notify` post can return None

        if "error" in response:
            error = response["error"]
            message = error.get("message", error) if isinstance(error, dict) else error
            raise MCPCallError(tool, arguments, f"JSON-RPC error: {message}")

        result = response.get("result")
        if result is None:
            raise MCPCallError(
                tool, arguments, f"response had neither 'result' nor 'error': {response!r}"
            )

        text = "".join(chunk.get("text", "") for chunk in result.get("content", []))
        if result.get("isError"):
            raise MCPCallError(tool, arguments, f"tool reported isError: {text or result!r}")
        if not text.strip():
            raise MCPCallError(tool, arguments, "empty response body")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise MCPCallError(
                tool, arguments, f"could not parse response body as JSON: {text[:200]!r}"
            ) from exc


class SpellslingerClient:
    """Typed convenience wrapper over a `Transport` for the two
    statistics tools `fetch_metagame.py` needs."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def statistics_archetypes(
        self, *, format: str, limit: int = 5000, min_level: str | None = None
    ) -> list[dict[str, Any]]:
        kwargs: dict[str, Any] = {"format": format, "limit": limit}
        if min_level is not None:
            kwargs["min_level"] = min_level
        result = self._transport.call("statistics_archetypes", **kwargs)
        return result if isinstance(result, list) else result.get("items", [])

    def statistics_decks(
        self,
        *,
        format: str,
        archetype_name: str | None = None,
        id: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int | None = None,
        include_cards: str | None = None,
    ) -> Any:
        """`limit`/`include_cards` are only sent when the caller passes
        them - a single-deck fetch by `id` needs neither, and the real
        server call the id-based fetch was ported from
        (`archetype_rates.py`'s `--secondary` path) never sends them."""
        kwargs: dict[str, Any] = {"format": format}
        if archetype_name is not None:
            kwargs["archetype_name"] = archetype_name
        if id is not None:
            kwargs["id"] = id
        if date_from is not None:
            kwargs["date_from"] = date_from
        if date_to is not None:
            kwargs["date_to"] = date_to
        if limit is not None:
            kwargs["limit"] = limit
        if include_cards is not None:
            kwargs["include_cards"] = include_cards
        return self._transport.call("statistics_decks", **kwargs)
