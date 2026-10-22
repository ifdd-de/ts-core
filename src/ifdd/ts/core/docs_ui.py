"""Swagger UI and ReDoc pages that work under a strict Content-Security-Policy.

Taken from ``ifdd.be.core.docs_ui`` without the OAuth2 login: this API is
called with tokens of the client credentials grant, so "Authorize" in
Swagger UI only takes a bearer token (no redirect page, no client id).

* The pages contain no inline script and no inline style; Swagger UI is
  started by ``docs_assets/ifdd/swagger-init.js``, which reads the URL of the
  OpenAPI document from a ``data-*`` attribute.
* Swagger UI and ReDoc are served from ``docs_assets/`` (exact versions,
  checked by SHA-256, see ``docs_assets/assets.json``): no CDN, no Internet.

The pages and the OpenAPI document are open; every data endpoint checks the
token.

=====================  ===================================
``/docs``              Swagger UI
``/redoc``             ReDoc
``/docs/assets/...``   the static files of both
=====================  ===================================

All paths are below the path prefix of the instance (``IFDD_TS_API_PATH``).
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.responses import HTMLResponse

ASSETS_DIR = Path(__file__).parent / "docs_assets"

DOCS_PATH = "/docs"
REDOC_PATH = "/redoc"
ASSETS_PATH = "/docs/assets"


def install_docs(app: FastAPI, title: str) -> None:
    """Add the documentation pages and their static files to an application.

    Args:
        app: Created with ``docs_url=None`` and ``redoc_url=None``.
        title: Title of the API, shown in the browser tab.
    """
    app.mount(ASSETS_PATH, StaticFiles(directory=ASSETS_DIR), name="docs-assets")

    async def swagger_ui(request: Request) -> HTMLResponse:
        """GET /docs."""
        return HTMLResponse(swagger_ui_html(_prefix(request), app.openapi_url, title))

    async def redoc(request: Request) -> HTMLResponse:
        """GET /redoc."""
        return HTMLResponse(redoc_html(_prefix(request), app.openapi_url, title))

    app.add_api_route(DOCS_PATH, swagger_ui, methods=["GET"], include_in_schema=False)
    app.add_api_route(REDOC_PATH, redoc, methods=["GET"], include_in_schema=False)


def _prefix(request: Request) -> str:
    """The ``root_path`` the application runs under, without a trailing slash."""
    return request.scope.get("root_path", "").rstrip("/")


def swagger_ui_html(prefix: str, openapi_url: str, title: str) -> str:
    """The Swagger UI page, without inline script or style."""
    a = _attribute
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} - Swagger UI</title>
<link rel="stylesheet" href="{a(prefix + ASSETS_PATH)}/swagger-ui/swagger-ui.css">
</head>
<body>
<noscript>Swagger UI needs JavaScript.
The OpenAPI document is at {escape(prefix + openapi_url)}.</noscript>
<div id="swagger-ui" data-openapi-url="{a(prefix + openapi_url)}"></div>
<script src="{a(prefix + ASSETS_PATH)}/swagger-ui/swagger-ui-bundle.js"></script>
<script src="{a(prefix + ASSETS_PATH)}/ifdd/swagger-init.js"></script>
</body>
</html>
"""


def redoc_html(prefix: str, openapi_url: str, title: str) -> str:
    """The ReDoc page, without inline script or style."""
    a = _attribute
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} - ReDoc</title>
<link rel="stylesheet" href="{a(prefix + ASSETS_PATH)}/ifdd/docs.css">
</head>
<body>
<noscript>ReDoc needs JavaScript.
The OpenAPI document is at {escape(prefix + openapi_url)}.</noscript>
<redoc spec-url="{a(prefix + openapi_url)}"></redoc>
<script src="{a(prefix + ASSETS_PATH)}/redoc/redoc.standalone.js"></script>
</body>
</html>
"""


def _attribute(value: str) -> str:
    """A value escaped for a double-quoted HTML attribute."""
    return escape(value, quote=True)
