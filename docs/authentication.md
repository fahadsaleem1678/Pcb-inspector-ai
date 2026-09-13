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

## Browser login and session handling

The React application now supports local mode (default) and opt-in Cognito authorization-code
login with PKCE S256, using pinned oidc-client-ts 3.5.0. The browser verifies its access token
with `/api/v1/auth/me` before opening the workspace. Browser and API auth modes and subjects
must match. Local mode remains a development identity, not authentication.

Copy `frontend/.env.example` to ignored `frontend/.env.local` and set the public settings:

```dotenv
VITE_AUTH_MODE=cognito
VITE_COGNITO_USER_POOL_ID=us-east-1_YourPoolId
VITE_COGNITO_CLIENT_ID=YourPublicAppClientId
VITE_COGNITO_DOMAIN=https://your-prefix.auth.us-east-1.amazoncognito.com
VITE_COGNITO_REDIRECT_URI=http://127.0.0.1:5173/auth/callback
VITE_COGNITO_LOGOUT_URI=http://127.0.0.1:5173/
VITE_COGNITO_SCOPES=openid profile your-resource/inspect
# Only when using resource binding, matching PCB_COGNITO_AUDIENCE:
# VITE_COGNITO_RESOURCE=https://your-api-resource
```

Use an existing authorized **public app client without a client secret**, enable the
Cognito authorization-code grant, and allow the exact callback/logout URLs and requested
scopes in that client. The hosted login handles account creation only if your pool permits
self-registration. This code does not create AWS resources or change account policies.
The callback must be `/auth/callback` and logout `/` on the site's own origin. HTTPS is
required except loopback development. The web server must serve the SPA on the callback
path; both Vite and the included Nginx config already do.

Vite compiles these values at build time. Restart development after changes, or rebuild the
static bundle for deployment. The frontend Dockerfile exposes the same public VITE_* build
arguments; runtime container environment variables do not reconfigure an already built SPA.
Never add a client secret, user password or token to a VITE_* value.

The OIDC library handles state, nonce, PKCE and token exchange. Access/ID/refresh tokens stay
in memory; only short-lived redirect state and its PKCE verifier use tab sessionStorage.
Reloading the page therefore requires signing in again (the hosted Cognito session may make
this quick). Selected inspection deep links survive a successful redirect. Callback code
and error parameters are removed from the address bar before processing the response.
The API's signature/issuer/client checks remain the authority for identity and ownership.

Refresh uses the refresh-token grant while the page is open, coalesces concurrent requests,
and rejects identity changes. A failed refresh or API 401 closes the workspace; uploads are
never automatically replayed. Late identity/refresh responses cannot restore a signed-out
session. Sign out clears local state immediately, attempts bounded refresh-token revocation,
then visits Cognito's logout endpoint even if revocation fails. This is local/hosted-session
logout, not proof that all previously issued JWTs are immediately invalid everywhere.

Image and JSON report requests use the same bearer-header transport as other API calls.
Images use temporary object URLs with cancellation and revocation on navigation/unmount;
reports download fetched blobs. Tokens never appear in image/download URLs. Same-origin
API routing is required, and credential-bearing fetches reject redirects.

## Acceptance and remaining work

`pnpm run test:auth` exercises the real OIDC client against isolated mock Cognito endpoints
on port 5175, on desktop and mobile. It verifies the S256 challenge against the token request's
verifier, state rejection before exchange, deep links, memory-only token storage, bearer
image/report delivery, successful refresh, failed refresh, failed revocation/logout and 401
without upload replay. These use synthetic tokens and mocked API identity responses; they
are not a live AWS integration test. Backend signed-token/ownership tests remain separate.
`pnpm run test:e2e` continues to verify the local workflow against the real local API/worker.
Auth traces go to ignored `frontend/auth-test-results/`, separate from the local suite.

Live Cognito signup/login/refresh/logout and two-user ownership acceptance are still pending
an actual pool/app-client configuration and authorized test accounts. S3/SQS/outbox and
production deployment remain separate work. No live AWS login has been claimed.

Offline signature checks do not implement immediate token revocation. Short token lifetimes,
revocation/session policy, JWKS refresh-abuse controls, rate limiting, HTTPS, deployment ingress
controls and auth telemetry need to be resolved before public deployment.

Sources:
- [AWS Cognito token verification](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-tokens-verifying-a-jwt.html)
- [PyJWT verification and JWKS behavior](https://pyjwt.readthedocs.io/en/latest/usage.html)

- [AWS Cognito authorization and PKCE](https://docs.aws.amazon.com/cognito/latest/developerguide/authorization-endpoint.html)
- [AWS Cognito token endpoint](https://docs.aws.amazon.com/cognito/latest/developerguide/token-endpoint.html)
- [AWS Cognito logout endpoint](https://docs.aws.amazon.com/cognito/latest/developerguide/logout-endpoint.html)
- [oidc-client-ts UserManager settings](https://authts.github.io/oidc-client-ts/classes/UserManagerSettingsStore.html)
