"""The Cloudflare Access guard."""

from __future__ import annotations

import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from main import create_app

TEAM = "grab-test.cloudflareaccess.com"
AUD = "test-aud-tag"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def token(key=KEY, aud=AUD, iss=f"https://{TEAM}", email="me@example.com", exp_in=3600) -> str:
    claims = {"aud": [aud], "iss": iss, "email": email, "exp": int(time.time()) + exp_in, "iat": int(time.time())}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "k1"})


@pytest.fixture
def guarded(settings):
    settings.dev_mode = False
    settings.cf_team_domain = TEAM
    settings.cf_aud = AUD
    settings.allowed_email = "me@example.com"
    app = create_app(settings)
    # Serve our test public key instead of fetching Cloudflare's certs.
    app.state.verifier._jwks = SimpleNamespace(get_signing_key_from_jwt=lambda _t: SimpleNamespace(key=KEY.public_key()))
    with TestClient(app) as c:
        yield c


def test_no_header_is_401(guarded):
    res = guarded.get("/api/system")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "unauthorized"


def test_valid_token_passes(guarded):
    res = guarded.get("/api/system", headers={"Cf-Access-Jwt-Assertion": token()})
    assert res.status_code == 200


@pytest.mark.parametrize(
    "bad",
    [
        token(aud="someone-else"),
        token(iss="https://evil.cloudflareaccess.com"),
        token(exp_in=-10),
        token(email="stranger@example.com"),
        "not-a-jwt",
    ],
)
def test_bad_tokens_are_401(guarded, bad):
    assert guarded.get("/api/jobs", headers={"Cf-Access-Jwt-Assertion": bad}).status_code == 401


def test_wrong_signing_key_is_401(guarded):
    assert guarded.get("/api/jobs", headers={"Cf-Access-Jwt-Assertion": token(key=OTHER_KEY)}).status_code == 401


def test_non_api_paths_are_not_guarded(guarded):
    assert guarded.get("/healthz").status_code == 200


def test_dev_mode_skips_the_check(client):
    assert client.get("/api/system").status_code == 200
