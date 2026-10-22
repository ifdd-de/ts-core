"""The one HTTP client of the process (VictoriaMetrics, type service).

TLS certificates are checked against the trust store of the system, not
against the bundle of the ``certifi`` package: the IFDD images add the local
CA of the proxy to the system store, and ``SSL_CERT_FILE`` still works.
"""

from __future__ import annotations

import ssl
from typing import Optional

import httpx

_client: Optional[httpx.AsyncClient] = None


def get_client() -> httpx.AsyncClient:
    """The shared client, created on first use."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(verify=ssl.create_default_context())
    return _client


async def close_client() -> None:
    """Close the shared client (at shutdown, and in tests)."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def set_client(client: Optional[httpx.AsyncClient]) -> None:
    """Replace the shared client, e.g. by one with a mock transport (tests)."""
    global _client
    _client = client
