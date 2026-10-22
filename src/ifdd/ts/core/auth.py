"""Access-token validation for the time series API.

Callers are services that get their token with the client credentials grant
from the realm and send it as ``Authorization: Bearer <token>``. The API
checks the signature against the realm's JWKS, the expiry, the audience
``IFDD_OIDC_JWKS_AUDIENCE``, the issuer ``IFDD_OIDC_ISSUER`` (if set) and that
the token is an access token (``typ`` is ``Bearer``; RFC 9068 forbids
accepting ID tokens). Roles are read from
``resource_access.<audience>.roles``; see :mod:`ifdd.ts.core.stores`.

The code follows ``ifdd.be.core.auth.oidc`` (a copy, by decision; see the
README). One difference: a validated token is cached for at most
``IFDD_TOKEN_CACHE_TTL`` seconds, and every cache hit checks the expiry
again, so an expired token is never accepted from the cache.
"""

from __future__ import annotations

import time
from typing import Optional

import jwt
from cachetools import TTLCache
from fastapi import Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from .config import get_settings
from .logging import setup_logger

logger = setup_logger(__name__)

# Value of the claim "typ" in Keycloak access tokens.
ACCESS_TOKEN_TYPE = "Bearer"
BEARER_SCHEME = "BearerToken"

bearer = HTTPBearer(
    auto_error=False,
    scheme_name=BEARER_SCHEME,
    description=(
        "An access token of the realm, got with the client credentials grant "
        "(see the introduction)."
    ),
)

_jwks_client: Optional[PyJWKClient] = None
_token_cache: Optional[TTLCache] = None
_issuer_warning_logged = False


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def _get_jwks_client() -> PyJWKClient:
    """One JWKS client per process; it caches the keys of the realm."""
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(get_settings().IFDD_OIDC_JWKS_URL)
    return _jwks_client


def _get_token_cache() -> TTLCache:
    global _token_cache
    if _token_cache is None:
        settings = get_settings()
        _token_cache = TTLCache(
            maxsize=settings.IFDD_TOKEN_CACHE_SIZE, ttl=settings.IFDD_TOKEN_CACHE_TTL
        )
    return _token_cache


def reset_auth() -> None:
    """Forget the JWKS client and the token cache (for tests)."""
    global _jwks_client, _token_cache, _issuer_warning_logged
    _jwks_client = None
    _token_cache = None
    _issuer_warning_logged = False


def _warn_once_without_issuer() -> None:
    global _issuer_warning_logged
    if not get_settings().IFDD_OIDC_ISSUER and not _issuer_warning_logged:
        logger.warning("IFDD_OIDC_ISSUER is not set: the token issuer is not checked")
        _issuer_warning_logged = True


def validate_token(token: str) -> dict:
    """Validate an access token and return its claims.

    Args:
        token: The bearer token of the request.

    Returns:
        The decoded claims.

    Raises:
        HTTPException: 401 with the reason for any failed check.
    """
    cache = _get_token_cache()
    claims = cache.get(token)
    if claims is not None:
        # The cache entry may outlive the token: check the expiry again.
        if claims.get("exp", 0) <= time.time():
            cache.pop(token, None)
            raise _unauthorized("Token has expired")
        return claims

    settings = get_settings()
    _warn_once_without_issuer()
    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=settings.oidc_algorithms,
            audience=settings.IFDD_OIDC_JWKS_AUDIENCE,
            issuer=settings.IFDD_OIDC_ISSUER or None,
            options={"require": ["exp"]},
        )
    except jwt.exceptions.ExpiredSignatureError:
        raise _unauthorized("Token has expired") from None
    except jwt.exceptions.InvalidAudienceError:
        raise _unauthorized(
            f"Invalid token audience. Expected: {settings.IFDD_OIDC_JWKS_AUDIENCE}"
        ) from None
    except jwt.exceptions.PyJWKClientError as error:
        logger.info(f"JWKS client error: {error}")
        raise _unauthorized(f"Unable to verify the token signature: {error}") from None
    except jwt.exceptions.InvalidTokenError as error:
        raise _unauthorized(f"Invalid token: {error}") from None

    if claims.get("typ") != ACCESS_TOKEN_TYPE:
        logger.info(f"Rejected token of type {claims.get('typ')!r}")
        raise _unauthorized("Invalid token: not an access token")
    cache[token] = claims
    return claims


def development_claims() -> dict:
    """The claims of the development user: both roles and the root pattern."""
    settings = get_settings()
    return {
        "preferred_username": "dev-user",
        "resource_access": {
            settings.IFDD_OIDC_JWKS_AUDIENCE: {
                "roles": [
                    settings.IFDD_TS_ROLE_READ,
                    settings.IFDD_TS_ROLE_WRITE,
                    settings.IFDD_CONTEXT_ROOT,
                ]
            }
        },
    }


async def token_claims(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
) -> dict:
    """FastAPI dependency: the claims of a valid access token (401 otherwise).

    With ``IFDD_TS_API_AUTH_ENABLED=false`` it returns the development user
    without looking at the request.
    """
    if not get_settings().IFDD_TS_API_AUTH_ENABLED:
        return development_claims()
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized("Not authenticated")
    # The first token of a key fetches the JWKS: keep that off the event loop.
    return await run_in_threadpool(validate_token, credentials.credentials)
