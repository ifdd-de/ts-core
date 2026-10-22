"""The OpenAPI document: introduction, tags, error answers.

Everything here only describes the API. :func:`error_responses` gives the
routers the documented error answers; :func:`build_openapi` puts the
document together.
"""

from __future__ import annotations

from typing import Any, Callable

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from .auth import BEARER_SCHEME
from .config import CoreSettings
from .version import __version__

REPOSITORY_URL = "https://github.com/ifdd-de/ts-core"

TAGS: list[dict[str, str]] = [
    {"name": "stores", "description": "The stores a client may read."},
    {"name": "series", "description": "The series of a store and their labels."},
    {
        "name": "samples",
        "description": (
            "Read the latest sample or the samples of a time range; write one "
            "sample or a list."
        ),
    },
    {"name": "meta", "description": "`/version` needs no token; `/whoami` shows your roles."},
]

_ERRORS: dict[int, tuple[str, str]] = {
    401: ("No valid access token.", "Not authenticated"),
    403: (
        "The token lacks the role, or no store pattern of the client matches the store.",
        "no store pattern of this client matches 'humidity.ops.example.ifdd.de'",
    ),
    404: ("No sample of the series in the searched time.",
          "no sample of this series in the searched time"),
    422: (
        "Invalid request: store name, time, labels, or a sample that does not fit "
        "the vocabulary of its property.",
        "samples[0]: unit 'https://unit/v1/unit/PERCENT_RH' is not applicable to "
        "'https://type/v1/climate.ops.example.ifdd.de/temperature'; use one of "
        "['https://unit/v1/unit/DEG_C']",
    ),
    502: (
        "VictoriaMetrics or the type service could not be reached or refused the call.",
        "VictoriaMetrics /api/v1/import: ConnectError('All connection attempts failed')",
    ),
}


def error_responses(*codes: int) -> dict[int, dict[str, Any]]:
    """The documented error answers for the given status codes."""
    return {
        code: {
            "description": _ERRORS[code][0],
            "content": {"application/json": {"example": {"detail": _ERRORS[code][1]}}},
        }
        for code in codes
    }


def _introduction(settings: CoreSettings) -> str:
    token_url = settings.IFDD_OIDC_TOKEN_URL or "<realm>/protocol/openid-connect/token"
    return f"""\
Samples of the time series of an IFDD node, stored in VictoriaMetrics.

**Access.** Only services call this API. A service gets an access token from
the realm with the client credentials grant and sends it as
`Authorization: Bearer <token>`:

```sh
curl -s -d grant_type=client_credentials -u "$CLIENT_ID:$CLIENT_SECRET" \\
     {token_url} | jq -r .access_token
```

In Swagger UI, paste the token under "Authorize". The token must be meant for
the client `{settings.IFDD_OIDC_JWKS_AUDIENCE}` (claim `aud`); its client roles
there decide what the caller may do:

* `{settings.IFDD_TS_ROLE_READ}` reads, `{settings.IFDD_TS_ROLE_WRITE}` writes;
* a role with a dot is a **store pattern**: it opens the store of that name
  and every store below it (`ops.example.ifdd.de` opens
  `temperature.ops.example.ifdd.de`). Without a matching pattern a store
  answers 403; lists leave such stores out.

**Stores.** A store is a named part of the time series database. Its name is
written like a DNS name. Grafana shows the series of all stores together;
the store decides only who may read and write through this API.

**Series.** A series is named by `name` (the metric name, only for people),
`ifdd_id` (the object in ifdd-be), `ifdd_property` (the property in a
vocabulary of the type service) and `ifdd_unit` (the unit), all full IRIs.

**Checks on write.** The property must be defined in the vocabulary of the
type service; the unit must be one of its applicable units (if it lists
any); the value must lie within its bounds (if it has any).

**Times** are ISO 8601 with an offset (`Z` or `+02:00`), at most to the
millisecond; answers are in UTC.

**Same time twice.** Samples are appended; nothing is replaced. If a series
gets two samples with the same time, the database keeps the larger value.
Sending the same sample again is therefore harmless.

ifdd-ts-core {__version__} · [source]({REPOSITORY_URL})
"""


def build_openapi(app: FastAPI, settings: CoreSettings) -> Callable[[], dict]:
    """A replacement for ``app.openapi`` that builds the full document once."""

    def openapi() -> dict:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=settings.API_TITLE,
            version=settings.IFDD_TS_API_VERSION,
            summary=settings.API_SUMMARY,
            description=_introduction(settings),
            routes=app.routes,
            tags=TAGS,
            license_info={
                "name": "BSD-3-Clause",
                "url": "https://opensource.org/license/bsd-3-clause",
            },
            servers=[{"url": settings.IFDD_TS_API_PATH}] if settings.IFDD_TS_API_PATH else None,
        )
        schema.setdefault("components", {}).setdefault("securitySchemes", {})[BEARER_SCHEME] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "An access token of the realm (client credentials grant).",
        }
        schema["security"] = [{BEARER_SCHEME: []}]
        app.openapi_schema = schema
        return schema

    return openapi
