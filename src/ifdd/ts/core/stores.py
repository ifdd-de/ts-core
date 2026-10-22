"""Stores and who may use them.

A *store* is a named part of the one VictoriaMetrics instance: every sample
carries the label ``ifdd_store``. The API sets that label itself on every
write and requires it on every read (VictoriaMetrics' ``extra_label``), so a
client never sees or touches a store it has no pattern for.

Store names are written like DNS names and read from the right, e.g.
``temperature.ops.example.ifdd.de``: at least two labels of lower-case
letters, digits and inner hyphens. Any such name is a store; a store exists
once a sample was written to it.

A *store pattern* is a client role (of ``IFDD_OIDC_JWKS_AUDIENCE``) whose name
contains a dot. It matches the store of the same name and every store below
it, compared at label boundaries: ``ops.example.ifdd.de`` matches
``temperature.ops.example.ifdd.de`` but not ``xops.example.ifdd.de``. The
root (``ifdd.de`` by default) matches every store.

Reading and writing are separate roles (``IFDD_TS_ROLE_READ``,
``IFDD_TS_ROLE_WRITE``); they apply to every store a client's patterns match.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from .config import get_settings

STORE_LABEL = "ifdd_store"

_LABEL = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")


class StoreNameError(ValueError):
    """Not a valid store name (HTTP 422)."""


class Forbidden(PermissionError):
    """The client lacks a role or a matching store pattern (HTTP 403)."""


def is_store_name(name: str) -> bool:
    """At least two labels, each lower-case letters, digits and inner hyphens."""
    labels = name.split(".")
    return len(labels) >= 2 and all(_LABEL.match(label) for label in labels)


def check_store_name(name: str) -> str:
    """Return ``name`` or raise :class:`StoreNameError`."""
    if not is_store_name(name):
        raise StoreNameError(
            f"{name!r} is not a store name: at least two labels of lower-case "
            "letters, digits and inner '-', separated by dots"
        )
    return name


def matches(name: str, pattern: str) -> bool:
    """A pattern matches its own name and every name below it."""
    return name == pattern or name.endswith("." + pattern)


@dataclass(frozen=True)
class Access:
    """Roles and store patterns of one client."""

    roles: frozenset[str]
    patterns: tuple[str, ...]

    @classmethod
    def from_token(cls, claims: Mapping) -> "Access":
        """Client roles of the audience; those with a dot are patterns."""
        audience = get_settings().IFDD_OIDC_JWKS_AUDIENCE
        roles = claims.get("resource_access", {}).get(audience, {}).get("roles", [])
        return cls(
            roles=frozenset(role for role in roles if "." not in role),
            patterns=tuple(sorted({role.lower() for role in roles if "." in role})),
        )

    def may_use(self, store: str) -> bool:
        """True if a pattern of the client matches the store."""
        return any(matches(store, pattern) for pattern in self.patterns)

    def can_read(self, store: str) -> bool:
        """The read role and a matching pattern."""
        return get_settings().IFDD_TS_ROLE_READ in self.roles and self.may_use(store)

    def require(self, role: str, store: str) -> None:
        """Raise :class:`Forbidden` unless the client has ``role`` and a pattern for ``store``."""
        if role not in self.roles:
            raise Forbidden(f"Insufficient permissions. Role {role} required.")
        if not self.may_use(store):
            raise Forbidden(f"no store pattern of this client matches {store!r}")

    def require_read(self, store: str) -> None:
        """Raise unless the client may read the store."""
        self.require(get_settings().IFDD_TS_ROLE_READ, store)

    def require_write(self, store: str) -> None:
        """Raise unless the client may write to the store."""
        self.require(get_settings().IFDD_TS_ROLE_WRITE, store)
