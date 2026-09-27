"""Tests for `scripts/spellslinger_client.py`'s real transport
(`MCPTransport`) - specifically that a JSON-RPC error, a tool result
flagged `isError`, or an empty/unparseable response body all raise a clear
exception naming the tool and its arguments, rather than `call` silently
returning `""` (which `response_items("")` then reads as zero decks -
silent undercounting, not a loud failure).

This is tooling, not the engine's own card-rules code, so the no-mocks
rule (`CLAUDE.md`) does not apply: the network layer (`urllib.request.
urlopen`) is faked, never the real server.
"""

from __future__ import annotations

import io
import json

import pytest
from scripts import spellslinger_client as sc


class _FakeHTTPResponse(io.BytesIO):
    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.headers: dict[str, str] = {}

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def _make_transport(monkeypatch: pytest.MonkeyPatch, bodies: list[bytes]) -> sc.MCPTransport:
    """A real `MCPTransport`, with `urlopen` faked to hand back `bodies` in
    order: the constructor's own `initialize` + `notifications/initialized`
    handshake consumes the first two, so callers script their `call()`
    response as the third (and any further calls after that)."""
    responses = iter(bodies)

    def fake_urlopen(request: object, timeout: float | None = None) -> _FakeHTTPResponse:
        return _FakeHTTPResponse(next(responses))

    monkeypatch.setattr(sc.urllib.request, "urlopen", fake_urlopen)
    return sc.MCPTransport("https://example.test/mcp")


_HANDSHAKE = [b'{"jsonrpc":"2.0","id":0,"result":{}}', b""]


def test_call_returns_parsed_json_on_a_normal_response(monkeypatch: pytest.MonkeyPatch):
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"content": [{"type": "text", "text": json.dumps([{"a": 1}])}]},
        }
    ).encode()
    transport = _make_transport(monkeypatch, [*_HANDSHAKE, body])
    assert transport.call("statistics_archetypes", format="modern") == [{"a": 1}]


def test_call_raises_on_json_rpc_error(monkeypatch: pytest.MonkeyPatch):
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "archetype not found"}}
    ).encode()
    transport = _make_transport(monkeypatch, [*_HANDSHAKE, body])
    with pytest.raises(sc.MCPCallError) as exc_info:
        transport.call("statistics_decks", format="modern", archetype_name="nope")
    message = str(exc_info.value)
    assert "statistics_decks" in message
    assert "archetype_name" in message
    assert "archetype not found" in message


def test_call_raises_on_tool_reported_is_error(monkeypatch: pytest.MonkeyPatch):
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [{"type": "text", "text": "unknown format 'klingon'"}],
                "isError": True,
            },
        }
    ).encode()
    transport = _make_transport(monkeypatch, [*_HANDSHAKE, body])
    with pytest.raises(sc.MCPCallError) as exc_info:
        transport.call("statistics_decks", format="klingon")
    message = str(exc_info.value)
    assert "statistics_decks" in message
    assert "unknown format" in message


def test_call_raises_on_empty_response_body(monkeypatch: pytest.MonkeyPatch):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"content": []}}).encode()
    transport = _make_transport(monkeypatch, [*_HANDSHAKE, body])
    with pytest.raises(sc.MCPCallError) as exc_info:
        transport.call("statistics_decks", format="modern")
    assert "statistics_decks" in str(exc_info.value)


def test_call_raises_on_unparseable_response_body(monkeypatch: pytest.MonkeyPatch):
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": "not json"}]}}
    ).encode()
    transport = _make_transport(monkeypatch, [*_HANDSHAKE, body])
    with pytest.raises(sc.MCPCallError) as exc_info:
        transport.call("statistics_decks", format="modern")
    assert "statistics_decks" in str(exc_info.value)


def test_call_raises_when_response_has_neither_result_nor_error(monkeypatch: pytest.MonkeyPatch):
    body = json.dumps({"jsonrpc": "2.0", "id": 1}).encode()
    transport = _make_transport(monkeypatch, [*_HANDSHAKE, body])
    with pytest.raises(sc.MCPCallError) as exc_info:
        transport.call("statistics_decks", format="modern")
    assert "statistics_decks" in str(exc_info.value)
