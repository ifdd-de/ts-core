"""Application factory.

The API is served below the path prefix ``IFDD_TS_API_PATH`` (``/tsapi`` by
default), so that it shares the host of Grafana behind the proxy without a
rewrite: the proxy passes ``/tsapi/...`` unchanged, and the application
mounts its routes there. Inside, every path is relative to the prefix (the
OpenAPI document names the prefix as its server).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Iterable, Optional

from fastapi import FastAPI
from fastapi.routing import APIRouter

from .config import CoreSettings, configure, get_settings
from .docs_ui import install_docs
from .errors import install_error_handlers
from .http import close_client
from .logging import setup_logger
from .openapi import build_openapi
from .routers import meta_router, samples_router
from .version import __version__


def create_app(
    settings: Optional[CoreSettings] = None,
    extra_routers: Optional[Iterable[APIRouter]] = None,
) -> FastAPI:
    """Create the application.

    Args:
        settings: Settings of the instance; registered with
            :func:`~ifdd.ts.core.config.configure`. Without them the settings
            are read from the environment.
        extra_routers: Instance-specific endpoints, included after the
            generic ones.

    Returns:
        The application for uvicorn (``uvicorn --factory
        ifdd.ts.core:create_app`` or an instance's ``app.main:app``).
    """
    if settings is not None:
        configure(settings)
    settings = get_settings()
    logger = setup_logger(__name__)
    logger.info(
        f"Starting {settings.API_TITLE} {settings.IFDD_TS_API_VERSION} "
        f"(ifdd-ts-core {__version__}) at {settings.IFDD_TS_API_PATH or '/'}"
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        """Close the HTTP client when the application stops."""
        yield
        await close_client()

    api = FastAPI(
        title=settings.API_TITLE,
        version=settings.IFDD_TS_API_VERSION,
        docs_url=None,
        redoc_url=None,
        swagger_ui_oauth2_redirect_url=None,
        root_path_in_servers=False,
        lifespan=None if settings.IFDD_TS_API_PATH else lifespan,
    )
    install_error_handlers(api)
    install_docs(api, settings.API_TITLE)
    api.include_router(meta_router)
    api.include_router(samples_router)
    for router in extra_routers or ():
        api.include_router(router)
    api.openapi = build_openapi(api, settings)

    if not settings.IFDD_TS_API_PATH:
        return api
    # A mounted application gets no lifespan events; the outer one runs them.
    outer = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    outer.mount(settings.IFDD_TS_API_PATH, api)
    outer.state.api = api
    return outer


def openapi_document(settings: Optional[CoreSettings] = None) -> dict:
    """The OpenAPI document of the API, e.g. for a documentation build.

    Args:
        settings: As for :func:`create_app`.

    Returns:
        The document as served at ``<IFDD_TS_API_PATH>/openapi.json``.
    """
    app = create_app(settings)
    return getattr(app.state, "api", app).openapi()
