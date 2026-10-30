"""``/version`` (no token) and ``/whoami`` (any valid token)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from .. import schemas
from ..auth import token_claims
from ..config import get_settings
from ..openapi import error_responses
from ..stores import Access

router = APIRouter(tags=["meta"])


@router.get(
    "/version",
    summary="Version of the instance (no token needed)",
    responses={200: {"content": {"application/json": {"example": {"version": "26.10.3"}}}}},
    openapi_extra={"security": []},
)
async def version() -> dict:
    """Return the version of this instance.

    Needs no token, so it suits health checks and tests of the route
    through the proxy.
    \f
    Returns:
        ``{"version": IFDD_TS_API_VERSION}``.
    """
    return {"version": get_settings().IFDD_TS_API_VERSION}


@router.get(
    "/whoami",
    response_model=schemas.WhoAmI,
    summary="What the API reads from your token",
    responses=error_responses(401),
)
async def whoami(claims: dict = Depends(token_claims)) -> schemas.WhoAmI:
    """Show the user name, client roles and store patterns of your token.

    Needs a valid access token, but no role. Use it when a request answers
    403: `client_roles` are the roles without a dot (`ifdd_ts_ro`,
    `ifdd_ts_rw`), `store_patterns` the roles with a dot; each pattern opens
    the store of that name and every store below it.
    \f
    Args:
        claims: The claims of the validated access token.
    """
    access = Access.from_token(claims)
    return schemas.WhoAmI(
        preferred_username=claims.get("preferred_username"),
        client_roles=sorted(access.roles),
        store_patterns=list(access.patterns),
    )
