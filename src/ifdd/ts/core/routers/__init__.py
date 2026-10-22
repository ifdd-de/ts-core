"""The routers of the time series API."""

from .meta import router as meta_router
from .samples import router as samples_router

__all__ = ["meta_router", "samples_router"]
