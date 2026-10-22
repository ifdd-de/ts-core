"""Token validation and the order of checks with authentication on.

Tokens are signed with a throwaway RSA key; the JWKS lookup is replaced, so
no identity provider is needed.
"""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from support import STORE_H, STORE_T, sample, settings

ISSUER = "https://id.example.org/realms/ifddtest"
AUDIENCE = "ifdd-ts-api"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _SigningKey:
    key = KEY.public_key()


class _FakeJWKClient:
    def __init__(self, *args, **kwargs):
        pass

    def get_signing_key_from_jwt(self, token):
        return _SigningKey()


def token(roles=(), typ="Bearer", iss=ISSUER, aud=AUDIENCE, key=KEY, lifetime=300):
    now = int(time.time())
    claims = {"iss": iss, "aud": aud, "sub": "sa-1", "iat": now, "exp": now + lifetime,
              "azp": "ifdd-ts-ingest", "preferred_username": "service-account-ifdd-ts-ingest",
              "resource_access": {AUDIENCE: {"roles": list(roles)}}}
    if typ is not None:
        claims["typ"] = typ
    return jwt.encode(claims, key, algorithm="RS256")


def bearer(value):
    return {"Authorization": f"Bearer {value}"}


@pytest.fixture
def secured(monkeypatch, services):
    from ifdd.ts.core import auth, create_app

    monkeypatch.setattr(auth, "PyJWKClient", _FakeJWKClient)
    app = create_app(settings(
        IFDD_TS_API_AUTH_ENABLED=True,
        IFDD_OIDC_JWKS_URL="https://id.example.org/certs",
        IFDD_OIDC_ISSUER=ISSUER,
        IFDD_OIDC_JWKS_AUDIENCE=AUDIENCE,
    ))
    services.install()
    with TestClient(app) as client:
        yield client


URL = f"/tsapi/stores/{STORE_T}/samples"
WRITER = ("ifdd_ts_rw", STORE_T)


def test_writer_with_pattern_writes(secured, services):
    response = secured.post(URL, json=sample(), headers=bearer(token(WRITER)))
    assert response.status_code == 200, response.text


def test_no_token_is_401(secured, services):
    response = secured.post(URL, json=sample())
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert not services.requests


@pytest.mark.parametrize(
    "bad, reason",
    [
        ({"aud": "ifddtest"}, "audience"),
        ({"iss": "https://elsewhere/realms/x"}, "issuer"),
        ({"typ": "ID"}, "not an access token"),
        ({"typ": None}, "not an access token"),
        ({"key": OTHER_KEY}, "Signature"),
        ({"lifetime": -10}, "expired"),
    ],
)
def test_invalid_tokens_are_401(secured, services, bad, reason):
    response = secured.post(URL, json=sample(), headers=bearer(token(WRITER, **bad)))
    assert response.status_code == 401
    assert reason.lower() in response.json()["detail"].lower()
    assert not services.requests


def test_401_comes_before_422(secured):
    response = secured.post("/tsapi/stores/BAD/samples", json={})
    assert response.status_code == 401


def test_invalid_store_name_before_roles(secured):
    response = secured.post("/tsapi/stores/BAD/samples", json=sample(), headers=bearer(token()))
    assert response.status_code == 422


def test_reader_may_not_write(secured, services):
    response = secured.post(URL, json=sample(),
                            headers=bearer(token(("ifdd_ts_ro", STORE_T))))
    assert response.status_code == 403
    assert "ifdd_ts_rw" in response.json()["detail"]
    assert not services.requests


def test_writer_of_one_store_may_not_write_to_another(secured, services):
    response = secured.post(f"/tsapi/stores/{STORE_H}/samples", json=sample(),
                            headers=bearer(token(WRITER)))
    assert response.status_code == 403
    assert "no store pattern" in response.json()["detail"]
    assert not services.requests


def test_writer_may_not_read(secured, services):
    response = secured.get(f"/tsapi/stores/{STORE_T}/series", headers=bearer(token(WRITER)))
    assert response.status_code == 403


def test_store_list_is_filtered(secured, services):
    services.store_values = [STORE_H, STORE_T]
    response = secured.get("/tsapi/stores", headers=bearer(token(("ifdd_ts_ro", STORE_T))))
    assert response.json() == [STORE_T]
    response = secured.get("/tsapi/stores", headers=bearer(token((STORE_T,))))
    assert response.status_code == 403


def test_whoami(secured):
    response = secured.get("/tsapi/whoami", headers=bearer(token(("ifdd_ts_ro", "IFDD.de"))))
    assert response.json() == {
        "preferred_username": "service-account-ifdd-ts-ingest",
        "client_roles": ["ifdd_ts_ro"],
        "store_patterns": ["ifdd.de"],
    }


def test_version_needs_no_token(secured):
    assert secured.get("/tsapi/version").status_code == 200


def test_cached_token_is_refused_once_expired(secured, monkeypatch):
    from ifdd.ts.core import auth

    value = token(WRITER, lifetime=5)
    assert secured.get("/tsapi/whoami", headers=bearer(value)).status_code == 200
    later = time.time() + 10
    monkeypatch.setattr(auth.time, "time", lambda: later)
    response = secured.get("/tsapi/whoami", headers=bearer(value))
    assert response.status_code == 401
    assert "expired" in response.json()["detail"]
