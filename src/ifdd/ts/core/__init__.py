"""ifdd.ts.core - shared runtime of the IFDD time series API."""

from .app import create_app
from .config import CoreSettings, configure, get_settings
from .version import __version__

__all__ = [
    "create_app",
    "CoreSettings",
    "configure",
    "get_settings",
    "__version__",
]
