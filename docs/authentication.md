# Cognito authentication boundary

The API now supports `PCB_AUTH_MODE=local` (default) and opt-in `cognito` mode.
Every inspection upload/read/history/image/report endpoint resolves a principal through one
dependency. `GET /api/v1/auth/me` exposes the current verified identity. Health and metrics
remain operational endpoints and must sit behind appropriate deployment networking.

## Local development

The default local identity is explicitly a development shortcut. It preserves existing local
jobs and the current React workflow. It is not user authentication. Non-local/test environments
still fail settings validation until the remaining deployment integrations are ready.

## Cognito API configuration

Set these in a private local `.env` when testing against an existing authorized Cognito user pool:

```dotenv
PCB_AUTH_MODE=cognito
PCB_COGNITO_USER_POOL_ID=us-east-1_YourPoolId
PCB_COGNITO_CLIENT_ID=YourAppClientId
PCB_COGNITO_REQUIRED_SCOPES=["your-resource/inspect"]
# Set only if your access tokens use resource binding:
# PCB_COGNITO_AUDIENCE=https://your-api-resource
```

Pool and client IDs must match the actual configured app. The example does not create a pool,
grant a scope or authorize any account. Missing/invalid configuration fails startup. Required
scopes default to empty until a resource-server policy is configured.

Supply the issued **access token** via `Authorization: Bearer ...` to API clients or Swagger's
Authorize control. The verifier accepts RS256 only, uses the configured pool's HTTPS JWKS,
verifies signature/issuer/expiry/issued-at, requires a user UUID subject and
`token_use=access`, checks `client_id`, and optionally checks audience and scopes.
Token-supplied issuer/JWKS URLs are never used for key discovery. ID tokens and client-credentials
machine subjects are not accepted.

JWKS documents are cached for five minutes. An unfamiliar signing-key ID causes a refresh to
support rotation; key retrieval times out after three seconds. A failed fetch returns 503,
invalid/missing tokens return 401 and missing configured scopes return 403. These paths never
fall back to the local identity. Namespace ownership by pool and subject prevents mixing
Cognito users with the development identity.

## Remaining work

This is the backend verification portion of M4. The React application currently runs in local
mode; managed login/signup, authorization-code flow with PKCE, session renewal/logout, protected
image/download delivery and browser auth acceptance are still to implement. Do not paste tokens
into frontend source or store them in repository files. Tests use ephemeral synthetic signing
keys and mock JWKS responses; live AWS login has not been tested.

Offline signature checks do not implement immediate token revocation. Short token lifetimes,
revocation/session policy, JWKS refresh-abuse controls, rate limiting, HTTPS, deployment ingress
controls and auth telemetry need to be resolved before public deployment.

Sources:
- [AWS Cognito token verification](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-tokens-verifying-a-jwt.html)
- [PyJWT verification and JWKS behavior](https://pyjwt.readthedocs.io/en/latest/usage.html)
