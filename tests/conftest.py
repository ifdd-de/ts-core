"""Shared fixtures.

``api`` is a test client of the application with a fake VictoriaMetrics and
a fake type service behind a mock HTTP transport; it records every request.
``vm_url`` is the URL of a real VictoriaMetrics for tests/test_vm_integration.py
(environment variable IFDD_TEST_VM_URL), started by the CI job.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("IFDD_TS_API_AUTH_ENABLED", "false")

from support import FakeServices, settings  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_state():
    """Every test starts with fresh settings, caches and HTTP client."""
    from ifdd.ts.core import auth, http, vocabulary
    from ifdd.ts.core.config import reset_settings

    reset_settings()
    auth.reset_auth()
    vocabulary.reset_cache()
    http.set_client(None)
    yield
    reset_settings()
    auth.reset_auth()
    vocabulary.reset_cache()
    http.set_client(None)


@pytest.fixture
def services():
    """The fake VictoriaMetrics and type service."""
    return FakeServices()


@pytest.fixture
def api(services):
    """A client of the application (auth off) talking to the fakes."""
    from fastapi.testclient import TestClient

    from ifdd.ts.core import create_app

    app = create_app(settings())
    services.install()
    with TestClient(app) as client:
        yield client


@pytest.fixture
def vm_url():
    url = os.environ.get("IFDD_TEST_VM_URL")
    if not url:
        pytest.skip("IFDD_TEST_VM_URL is not set (no VictoriaMetrics)")
    return url
