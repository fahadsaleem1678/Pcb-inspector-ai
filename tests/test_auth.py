import io
import json
import time
from urllib.error import URLError
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from pydantic import ValidationError

from pcb_inspector.api import create_app
from pcb_inspector.config import Settings
from pcb_inspector.worker import Worker

POOL = "us-east-1_TestPool"
CLIENT_ID = "testclient123"
ISSUER = f"https://cognito-idp.us-east-1.amazonaws.com/{POOL}"
SUBJECT = "11111111-1111-1111-1111-111111111111"


@pytest.fixture(scope="module")
def keys():
    return [rsa.generate_private_key(public_exponent=65537, key_size=2048) for _ in range(2)]


def jwk(key, kid):
    result = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    return {**result, "kid": kid, "use": "sig", "alg": "RS256"}


def token(keys, changes=None, remove=(), key_index=0, kid="key-1"):
    now = int(time.time())
    claims = {
        "sub": SUBJECT,
        "iss": ISSUER,
        "iat": now - 1,
        "exp": now + 300,
        "client_id": CLIENT_ID,
        "token_use": "access",
        "scope": "pcb/inspect openid",
        **(changes or {}),
    }
    for claim in remove:
        claims.pop(claim, None)
    return jwt.encode(
        claims, keys[key_index], algorithm="RS256", headers={"kid": kid} if kid is not None else {}
    )


@pytest.fixture
def authenticated(settings, keys, monkeypatch):
    cognito = Settings(
        **{
            **settings.model_dump(),
            "auth_mode": "cognito",
            "cognito_user_pool_id": POOL,
            "cognito_client_id": CLIENT_ID,
            "cognito_required_scopes": ("pcb/inspect",),
        },
        _env_file=None,
    )
    state = {"keys": [jwk(keys[0], "key-1")], "requests": [], "offline": False}

    def fetch(request, **kwargs):
        state["requests"].append(request.full_url)
        assert request.full_url == ISSUER + "/.well-known/jwks.json"
        assert kwargs["timeout"] == 3
        if state["offline"]:
            raise URLError("simulated key service outage")
        return io.BytesIO(json.dumps({"keys": state["keys"]}).encode())

    monkeypatch.setattr("urllib.request.urlopen", fetch)
    app = create_app(cognito)
    with TestClient(app) as client:
        yield client, app, cognito, state


def auth_header(encoded):
    return {"Authorization": f"Bearer {encoded}"}


def test_valid_access_token_and_jwks_cache(authenticated, keys):
    client, app, settings, state = authenticated
    for _ in range(2):
        response = client.get("/api/v1/auth/me", headers=auth_header(token(keys)))
        assert response.status_code == 200
        assert response.json() == {
            "subject": SUBJECT,
            "owner_id": f"cognito:{POOL}:{SUBJECT}",
            "auth_mode": "cognito",
            "scopes": ["pcb/inspect", "openid"],
        }
    assert len(state["requests"]) == 1


@pytest.mark.parametrize(
    "changes,remove",
    [
        ({"iss": "https://attacker.invalid/pool"}, ()),
        ({"client_id": "anotherclient"}, ()),
        ({"token_use": "id", "aud": CLIENT_ID}, ()),
        ({"exp": 1}, ()),
        ({"iat": int(time.time()) + 1000}, ()),
        ({"nbf": int(time.time()) + 1000}, ()),
        ({"sub": "machine-client"}, ()),
        ({"scope": ["pcb/inspect"]}, ()),
        ({}, ("exp",)),
        ({}, ("iat",)),
        ({}, ("sub",)),
        ({}, ("client_id",)),
        ({}, ("token_use",)),
        ({"exp": str(int(time.time()) + 300)}, ()),
    ],
)
def test_invalid_claims_are_rejected(authenticated, keys, changes, remove):
    client, _, _, _ = authenticated
    response = client.get("/api/v1/auth/me", headers=auth_header(token(keys, changes, remove)))
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["detail"] == "A valid Cognito access token is required"


def test_signature_algorithm_missing_header_and_missing_credentials(authenticated, keys):
    client, _, _, state = authenticated
    assert client.get("/api/v1/inspections").status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Basic abc"}).status_code == 401
    assert client.get("/api/v1/auth/me", headers=auth_header("invalid")).status_code == 401
    assert (
        client.get("/api/v1/auth/me", headers=auth_header(token(keys, kid=None))).status_code == 401
    )
    symmetric = jwt.encode(
        {"sub": SUBJECT},
        "test-secret-that-is-at-least-32-bytes",
        algorithm="HS256",
        headers={"kid": "key-1"},
    )
    assert client.get("/api/v1/auth/me", headers=auth_header(symmetric)).status_code == 401
    assert state["requests"] == []
    # Select key 1 in the header but sign with key 2.
    assert (
        client.get("/api/v1/auth/me", headers=auth_header(token(keys, key_index=1))).status_code
        == 401
    )


def test_key_rotation_refresh_and_unknown_key(authenticated, keys):
    client, _, _, state = authenticated
    assert client.get("/api/v1/auth/me", headers=auth_header(token(keys))).status_code == 200
    state["keys"].append(jwk(keys[1], "key-2"))
    assert (
        client.get(
            "/api/v1/auth/me", headers=auth_header(token(keys, key_index=1, kid="key-2"))
        ).status_code
        == 200
    )
    assert len(state["requests"]) == 2
    assert (
        client.get("/api/v1/auth/me", headers=auth_header(token(keys, kid="missing"))).status_code
        == 401
    )


def test_scope_and_jwks_outage_fail_closed(authenticated, keys):
    client, app, settings, state = authenticated
    response = client.get(
        "/api/v1/inspections", headers=auth_header(token(keys, {"scope": "openid"}))
    )
    assert response.status_code == 403
    # Use a fresh authenticator so a cached valid key cannot mask the outage.
    from pcb_inspector.auth import Authenticator

    app.state.authenticator = Authenticator(settings)
    state["offline"] = True
    response = client.get("/api/v1/auth/me", headers=auth_header(token(keys)))
    assert response.status_code == 503
    assert response.headers["retry-after"] == "30"
    assert "simulated" not in response.text


def test_every_inspection_route_uses_verified_owner(authenticated, keys, png):
    client, app, settings, _ = authenticated
    first = auth_header(token(keys))
    second = auth_header(token(keys, {"sub": str(uuid4())}))
    denied = client.post("/api/v1/inspections/upload", files={"file": ("x.png", png)})
    assert denied.status_code == 401
    assert app.state.repository.history(settings.local_user_id, 10, 0) == []
    response = client.post(
        "/api/v1/inspections/upload", files={"file": ("x.png", png)}, headers=first
    )
    assert response.status_code == 202
    job_id = response.json()["inspection_id"]
    assert Worker(app.state.repository, app.state.storage, settings).run_once()
    for suffix in ["", "/image", "/results", "/report"]:
        url = f"/api/v1/inspections/{job_id}{suffix}"
        assert client.get(url, headers=first).status_code == 200
        assert client.get(url, headers=second).status_code == 404
        assert client.get(url).status_code == 401
    assert len(client.get("/api/v1/inspections", headers=first).json()["items"]) == 1
    assert client.get("/api/v1/inspections", headers=second).json()["items"] == []
    # A caller-supplied local user header cannot bypass JWT ownership.
    assert client.get("/api/v1/inspections", headers={"X-User-ID": SUBJECT}).status_code == 401


def test_optional_resource_audience(authenticated, keys):
    client, app, settings, _ = authenticated
    from pcb_inspector.auth import Authenticator

    app.state.authenticator = Authenticator(
        settings.model_copy(update={"cognito_audience": "pcb-api"})
    )
    assert client.get("/api/v1/auth/me", headers=auth_header(token(keys))).status_code == 401
    assert (
        client.get(
            "/api/v1/auth/me", headers=auth_header(token(keys, {"aud": "wrong"}))
        ).status_code
        == 401
    )
    assert (
        client.get(
            "/api/v1/auth/me", headers=auth_header(token(keys, {"aud": "pcb-api"}))
        ).status_code
        == 200
    )


def test_local_mode_remains_explicit_and_configuration_is_validated(client):
    assert client.get("/api/v1/auth/me").json()["auth_mode"] == "local"
    with pytest.raises(ValidationError):
        Settings(_env_file=None, auth_mode="cognito")
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            auth_mode="cognito",
            cognito_user_pool_id="https://evil.invalid",
            cognito_client_id=CLIENT_ID,
        )
