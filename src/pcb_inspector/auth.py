"""Local identity and opt-in Cognito access-token authentication."""

import math
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient, PyJWKClientConnectionError

from pcb_inspector.config import Settings

bearer = HTTPBearer(auto_error=False, description="Cognito user-pool access token (RS256)")


@dataclass(frozen=True)
class Principal:
    subject: str
    owner_id: str
    auth_mode: str
    scopes: tuple[str, ...] = ()


class Authenticator:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.issuer: str | None = None
        self.jwks: PyJWKClient | None = None
        if settings.auth_mode == "cognito":
            pool_id = settings.cognito_user_pool_id
            assert pool_id is not None
            region = pool_id.split("_", 1)[0]
            domain = "amazonaws.com.cn" if region.startswith("cn-") else "amazonaws.com"
            self.issuer = f"https://cognito-idp.{region}.{domain}/{pool_id}"
            self.jwks = PyJWKClient(
                f"{self.issuer}/.well-known/jwks.json",
                cache_jwk_set=True,
                cache_keys=False,
                lifespan=300,
                timeout=3,
            )

    def authenticate(self, credentials: HTTPAuthorizationCredentials | None) -> Principal:
        if self.settings.auth_mode == "local":
            return Principal(
                subject=self.settings.local_user_id,
                owner_id=self.settings.local_user_id,
                auth_mode="local",
            )
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise self.unauthorized()
        token = credentials.credentials
        try:
            if len(token) > 16384:
                raise ValueError("Token exceeds size limit")
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if header.get("alg") != "RS256" or not isinstance(kid, str) or not 1 <= len(kid) <= 128:
                raise ValueError("Unsupported token header")
            assert self.jwks is not None and self.issuer is not None
            key = self.jwks.get_signing_key(kid)
            # Access tokens bind the application via client_id; ID-token aud is not a substitute.
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                issuer=self.issuer,
                audience=self.settings.cognito_audience,
                options={
                    "require": ["exp", "iat", "iss", "sub", "token_use", "client_id"],
                    "verify_aud": self.settings.cognito_audience is not None,
                },
            )
            if (
                claims["token_use"] != "access"
                or claims["client_id"] != self.settings.cognito_client_id
            ):
                raise ValueError("Wrong token use or application")
            for field in ("exp", "iat"):
                value = claims[field]
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                ):
                    raise ValueError("Invalid numeric date")
            if claims["exp"] <= claims["iat"]:
                raise ValueError("Invalid validity interval")
            # This API represents signed-in users, not client-credentials machine identities.
            subject = str(UUID(claims["sub"]))
            scope_claim = claims.get("scope", "")
            if not isinstance(scope_claim, str):
                raise ValueError("Invalid scope claim")
            scopes = tuple(scope_claim.split())
        except PyJWKClientConnectionError as exc:
            raise HTTPException(
                503,
                "Identity verification is temporarily unavailable",
                headers={"Retry-After": "30"},
            ) from exc
        except (jwt.PyJWTError, ValueError, TypeError, KeyError, AttributeError) as exc:
            raise self.unauthorized() from exc
        if not set(self.settings.cognito_required_scopes).issubset(scopes):
            raise HTTPException(403, "The access token does not grant the required scope")
        return Principal(
            subject=subject,
            owner_id=f"cognito:{self.settings.cognito_user_pool_id}:{subject}",
            auth_mode="cognito",
            scopes=scopes,
        )

    @staticmethod
    def unauthorized() -> HTTPException:
        return HTTPException(
            401,
            "A valid Cognito access token is required",
            headers={"WWW-Authenticate": "Bearer"},
        )


def current_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Principal:
    # A synchronous dependency keeps bounded JWKS requests off the API event loop.
    authenticator: Authenticator = request.app.state.authenticator
    return authenticator.authenticate(credentials)


PrincipalDependency = Annotated[Principal, Depends(current_principal)]
