"""The path prefix, the documentation pages and the OpenAPI document."""

import re

import pytest
from fastapi.testclient import TestClient

from support import settings


def _client(**overrides):
    from ifdd.ts.core import create_app

    return TestClient(create_app(settings(**overrides)))


def test_everything_is_below_the_prefix(api):
    assert api.get("/tsapi/version").json() == {"version": "26.10.3"}
    assert api.get("/version").status_code == 404
    assert api.get("/openapi.json").status_code == 404
    assert api.get("/docs").status_code == 404


def test_other_prefix_and_no_prefix():
    with _client(IFDD_TS_API_PATH="/ts/api") as client:
        assert client.get("/ts/api/version").status_code == 200
        assert client.get("/ts/api/openapi.json").json()["servers"] == [{"url": "/ts/api"}]
    with _client(IFDD_TS_API_PATH="") as client:
        assert client.get("/version").status_code == 200
        assert "servers" not in client.get("/openapi.json").json()


@pytest.mark.parametrize("path", ["tsapi", "/tsapi/", "/TSAPI", "/ts api"])
def test_invalid_prefix(path):
    with pytest.raises(ValueError):
        settings(IFDD_TS_API_PATH=path)


def test_openapi_document(api):
    document = api.get("/tsapi/openapi.json").json()
    assert document["servers"] == [{"url": "/tsapi"}]
    assert sorted(document["paths"]) == [
        "/stores",
        "/stores/{store}/samples",
        "/stores/{store}/samples/batch",
        "/stores/{store}/samples/range",
        "/stores/{store}/series",
        "/version",
        "/whoami",
    ]
    assert set(document["paths"]["/stores/{store}/samples"]) == {"get", "post"}
    assert document["components"]["securitySchemes"]["BearerToken"]["scheme"] == "bearer"
    assert document["security"] == [{"BearerToken": []}]
    assert document["paths"]["/version"]["get"]["security"] == []
    assert "client credentials" in document["info"]["description"]
    assert document["info"]["license"]["name"] == "BSD-3-Clause"


@pytest.mark.parametrize("page", ["/tsapi/docs", "/tsapi/redoc"])
def test_pages_have_no_inline_script_or_style(api, page):
    html = api.get(page).text
    assert "<style" not in html and " style=" not in html
    for tag in re.findall(r"<script[^>]*>", html):
        assert "src=" in tag
    for url in re.findall(r'(?:src|href|spec-url|data-openapi-url)="([^"]+)"', html):
        assert url.startswith("/tsapi/"), url
        assert api.get(url).status_code == 200, url


def test_swagger_has_no_oauth_login(api):
    html = api.get("/tsapi/docs").text
    assert "client-id" not in html and "oauth2" not in html
    assert api.get("/tsapi/docs/oauth2-redirect").status_code == 404
