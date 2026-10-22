"""The version of this package, read from its installed metadata.

``pyproject.toml`` is the only place that names the version; everything else
(``ifdd.ts.core.__version__``, the default of ``IFDD_TS_API_VERSION``, the
OpenAPI description) reads it from the metadata of the installed
distribution.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

DISTRIBUTION = "ifdd-ts-core"


def package_version() -> str:
    """Return the version of the installed ``ifdd-ts-core`` distribution.

    Returns:
        The version from the package metadata, or ``"0+unknown"`` when the
        package is imported without being installed.
    """
    try:
        return version(DISTRIBUTION)
    except PackageNotFoundError:
        return "0+unknown"


__version__ = package_version()
