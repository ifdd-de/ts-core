"""Settings of the time series API and the settings registry.

An instance may subclass :class:`CoreSettings` and register its settings with
:func:`configure` before the application is created. Every part of
ifdd.ts.core reads the settings through :func:`get_settings` at call time,
never at import time, so import order does not matter.

All values come from the environment or from ``.env`` (pydantic-settings);
unknown variables are ignored.
"""

from __future__ import annotations

import re
from typing import Optional, Type

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .version import __version__

_PATH = re.compile(r"^(/[a-z0-9][a-z0-9-]*)+$")


class CoreSettings(BaseSettings):
    """Settings of an ifdd-ts-api instance.

    The ones an instance usually sets in its ``.env``:

    * ``IFDD_TS_API_PATH`` -- the path prefix the API is served under;
    * ``IFDD_OIDC_ISSUER``, ``IFDD_OIDC_JWKS_URL``, ``IFDD_OIDC_TOKEN_URL``
      and ``IFDD_OIDC_JWKS_AUDIENCE`` -- the realm and the client whose
      roles the API checks;
    * ``IFDD_TS_VM_URL`` -- VictoriaMetrics;
    * ``IFDD_TYPE_URL`` -- the type service whose vocabularies define the
      properties of the samples.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # API
    API_TITLE: str = "IFDD Time Series API"
    API_SUMMARY: str = "Samples of the time series of an IFDD node"
    # Version of the instance; the template sets it from ifdd_ts_api_version.
    IFDD_TS_API_VERSION: str = __version__
    # Path prefix of every endpoint, e.g. /tsapi; "" serves at the root.
    IFDD_TS_API_PATH: str = "/tsapi"

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # OIDC. Only access tokens of the client credentials grant are expected:
    # the roles below are given to service accounts only.
    IFDD_TS_API_AUTH_ENABLED: bool = True
    # Expected "iss", e.g. https://id/realms/ifddtest. Empty: not checked
    # (a warning is logged once).
    IFDD_OIDC_ISSUER: str = ""
    IFDD_OIDC_JWKS_URL: str = ""
    # Only shown in the API description: where a client gets its token.
    IFDD_OIDC_TOKEN_URL: str = ""
    # The client that carries the roles below; it is the required "aud".
    IFDD_OIDC_JWKS_AUDIENCE: str = "ifdd-ts-api"
    IFDD_OIDC_JWKS_ALGORITHM: str = "RS256"
    IFDD_TOKEN_CACHE_SIZE: int = 1000
    IFDD_TOKEN_CACHE_TTL: int = 300

    # Roles: client roles of IFDD_OIDC_JWKS_AUDIENCE. Roles with a dot are
    # store patterns (see stores.py).
    IFDD_TS_ROLE_READ: str = "ifdd_ts_ro"
    IFDD_TS_ROLE_WRITE: str = "ifdd_ts_rw"
    # Store pattern of the development user (IFDD_TS_API_AUTH_ENABLED=false).
    IFDD_CONTEXT_ROOT: str = "ifdd.de"

    # VictoriaMetrics
    IFDD_TS_VM_URL: str = "http://victoriametrics:8428"
    IFDD_TS_VM_TIMEOUT: float = 30.0

    # Vocabularies of the type service: every property is checked there.
    IFDD_TYPE_URL: str = "http://type/v1"
    IFDD_TS_VOCABULARY_CACHE_TTL: int = 300
    IFDD_TS_VOCABULARY_TIMEOUT: float = 10.0

    # Limits per request: samples written or read, series listed.
    IFDD_TS_MAX_ITEMS: int = 10000
    # Default time range of /stores and /series when no start is given.
    IFDD_TS_DEFAULT_RANGE_DAYS: int = 30
    # How far back the latest sample is searched when max_age is not given.
    IFDD_TS_LOOKBACK_DAYS: int = 3660

    @field_validator("IFDD_TS_API_PATH")
    @classmethod
    def _path(cls, value: str) -> str:
        """Empty, or segments of lower-case letters, digits and '-'."""
        if value and not _PATH.match(value):
            raise ValueError(
                "IFDD_TS_API_PATH must be empty or like /tsapi "
                "(lower-case letters, digits, '-', no trailing slash)"
            )
        return value

    @field_validator("IFDD_TS_MAX_ITEMS", "IFDD_TS_DEFAULT_RANGE_DAYS", "IFDD_TS_LOOKBACK_DAYS")
    @classmethod
    def _positive(cls, value: int) -> int:
        """Limits and ranges must be at least 1."""
        if value < 1:
            raise ValueError("must be at least 1")
        return value

    @property
    def oidc_algorithms(self) -> list[str]:
        """The signature algorithms accepted for tokens, as PyJWT expects them."""
        return [self.IFDD_OIDC_JWKS_ALGORITHM]


_settings: Optional[CoreSettings] = None
_settings_class: Type[CoreSettings] = CoreSettings


def configure(settings: CoreSettings) -> CoreSettings:
    """Register the settings every part of ifdd.ts.core will use.

    Args:
        settings: The settings of the instance, usually a subclass of
            :class:`CoreSettings`.

    Returns:
        The same settings object.
    """
    global _settings
    _settings = settings
    return settings


def get_settings() -> CoreSettings:
    """The registered settings; read from the environment on first use."""
    global _settings
    if _settings is None:
        _settings = _settings_class()
    return _settings


def reset_settings() -> None:
    """Forget the registered settings (for tests)."""
    global _settings
    _settings = None
