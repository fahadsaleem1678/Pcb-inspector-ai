import { afterEach, describe, expect, it, vi } from 'vitest';
import { User } from 'oidc-client-ts';
import { BrowserAuth, readAuthConfig } from './auth';
const env = {
  VITE_AUTH_MODE: 'cognito',
  VITE_COGNITO_USER_POOL_ID: 'us-east-1_TestPool',
  VITE_COGNITO_CLIENT_ID: 'publicclient',
  VITE_COGNITO_DOMAIN: 'https://login.example.com',
};
const config = readAuthConfig(env, 'http://localhost:3000');
const principal = {
  subject: 'user-one',
  owner_id: 'cognito:user-one',
  auth_mode: 'cognito',
  scopes: [],
};
function user(expires = 3600, token = 'access-one', sub = 'user-one') {
  return new User({
    access_token: token,
    token_type: 'Bearer',
    refresh_token: 'refresh-one',
    expires_at: Math.floor(Date.now() / 1000) + expires,
    profile: { sub, iss: 'issuer', aud: 'client', exp: 9999999999, iat: 1 },
  });
}
const sessions: BrowserAuth[] = [];
function setup(value = user()) {
  const manager = {
    getUser: vi.fn().mockResolvedValue(value),
    signinRedirectCallback: vi.fn().mockResolvedValue(value),
    signinRedirect: vi.fn().mockResolvedValue(undefined),
    signinSilent: vi.fn().mockResolvedValue(user(3600, 'access-two')),
    removeUser: vi.fn().mockResolvedValue(undefined),
    clearStaleState: vi.fn().mockResolvedValue(undefined),
  };
  const http = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify(principal)));
  const session = new BrowserAuth(config, manager, http);
  sessions.push(session);
  return { manager, http, session };
}
afterEach(() => {
  sessions.splice(0).forEach((session) => session.invalidate());
  vi.useRealTimers();
  window.history.replaceState({}, '', '/');
});

describe('authentication configuration', () => {
  it('defaults only an absent mode to local and requires public Cognito settings', () => {
    expect(readAuthConfig({}, 'http://localhost:3000')).toEqual({ mode: 'local' });
    expect(config.mode).toBe('cognito');
  });
  it.each([
    { VITE_AUTH_MODE: 'typo' },
    { VITE_COGNITO_CLIENT_ID: '' },
    { VITE_COGNITO_DOMAIN: 'http://login.example.com' },
    { VITE_COGNITO_DOMAIN: 'https://user:password@login.example.com' },
    { VITE_COGNITO_DOMAIN: 'https://login.example.com/other' },
    { VITE_COGNITO_REDIRECT_URI: 'https://elsewhere.example/auth/callback' },
    { VITE_COGNITO_REDIRECT_URI: 'http://localhost:3000/auth/callback?token=x' },
    { VITE_COGNITO_SCOPES: 'profile' },
    { VITE_COGNITO_RESOURCE: 'http://api.example' },
  ])('rejects unsafe or inconsistent settings %j', (override) => {
    expect(() => readAuthConfig({ ...env, ...override }, 'http://localhost:3000')).toThrow();
  });
});

describe('browser sessions', () => {
  it('verifies the API identity once even with repeated initialization', async () => {
    const { session, http, manager } = setup();
    await Promise.all([session.initialize(), session.initialize()]);
    expect(http).toHaveBeenCalledTimes(1);
    expect(http.mock.calls[0][1]?.headers).toEqual({ Authorization: 'Bearer access-one' });
    expect(manager.getUser).toHaveBeenCalledTimes(1);
    expect(session.getSnapshot()).toEqual({ status: 'ready', principal });
  });
  it.each([
    { ...principal, subject: 'another-user' },
    { ...principal, auth_mode: 'local' },
  ])('rejects an identity mismatch %j', async (identity) => {
    const { session, http } = setup();
    http.mockResolvedValue(new Response(JSON.stringify(identity)));
    await session.initialize();
    expect(session.getSnapshot().status).toBe('error');
    await expect(session.accessToken()).rejects.toThrow('Sign in');
  });
  it('coalesces concurrent refreshes and uses the new access token', async () => {
    vi.useFakeTimers();
    const { session, manager } = setup(user(31));
    await session.initialize();
    vi.setSystemTime(Date.now() + 2000);
    expect(await Promise.all([session.accessToken(), session.accessToken()])).toEqual([
      'access-two',
      'access-two',
    ]);
    expect(manager.signinSilent).toHaveBeenCalledTimes(1);
  });
  it('clears the workspace after refresh rejection', async () => {
    vi.useFakeTimers();
    const { session, manager } = setup(user(31));
    await session.initialize();
    manager.signinSilent.mockRejectedValue(new Error('invalid_grant'));
    vi.setSystemTime(Date.now() + 2000);
    await expect(session.accessToken()).rejects.toThrow();
    expect(session.getSnapshot().status).toBe('error');
    expect(manager.removeUser).toHaveBeenCalled();
  });
  it('rejects a refreshed identity change', async () => {
    vi.useFakeTimers();
    const { session, manager } = setup(user(31));
    await session.initialize();
    manager.signinSilent.mockResolvedValue(user(3600, 'changed-token', 'another-user'));
    vi.setSystemTime(Date.now() + 2000);
    await expect(session.accessToken()).rejects.toThrow();
    expect(session.getSnapshot().status).toBe('error');
  });
  it('does not revive a session when an in-flight refresh finishes after logout', async () => {
    vi.useFakeTimers();
    const { session, manager } = setup(user(31));
    await session.initialize();
    let finish!: (value: User) => void;
    manager.signinSilent.mockReturnValue(
      new Promise((resolve) => {
        finish = resolve;
      }),
    );
    vi.setSystemTime(Date.now() + 2000);
    const pending = session.accessToken();
    session.invalidate();
    finish(user());
    await expect(pending).rejects.toThrow('Session ended');
    expect(session.getSnapshot().status).toBe('signed_out');
  });
  it('does not revive a session when identity verification finishes after logout', async () => {
    const { session, http } = setup();
    let finish!: (value: Response) => void;
    http.mockReturnValue(
      new Promise((resolve) => {
        finish = resolve;
      }),
    );
    const pending = session.initialize();
    await vi.waitFor(() => expect(http).toHaveBeenCalled());
    session.invalidate();
    finish(new Response(JSON.stringify(principal)));
    await pending;
    expect(session.getSnapshot().status).toBe('signed_out');
  });
  it('removes callback credentials before handling a failed callback', async () => {
    const { session, manager } = setup();
    window.history.replaceState({}, '', '/auth/callback?code=secret&state=invalid');
    manager.signinRedirectCallback.mockRejectedValue(new Error('bad state'));
    await session.initialize();
    expect(window.location.search).toBe('');
    expect(session.getSnapshot().status).toBe('error');
  });
});
