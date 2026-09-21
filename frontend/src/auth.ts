import { serviceUrl } from './serviceUrl';
import { InMemoryWebStorage, UserManager, WebStorageStateStore } from 'oidc-client-ts';
import type { User } from 'oidc-client-ts';
import type { components } from './generated/api';
export type Principal = components['schemas']['Principal'];
type CognitoConfig = {
  mode: 'cognito';
  authority: string;
  domain: string;
  clientId: string;
  redirectUri: string;
  logoutUri: string;
  scope: string;
  resource?: string;
};
export type AuthConfig = { mode: 'local' } | CognitoConfig;

export function readAuthConfig(
  env: Record<string, string | undefined>,
  origin: string,
): AuthConfig {
  const mode = env.VITE_AUTH_MODE || 'local';
  if (mode === 'local') return { mode };
  if (mode !== 'cognito') throw new Error('VITE_AUTH_MODE must be local or cognito.');
  const pool = env.VITE_COGNITO_USER_POOL_ID || '';
  const match = /^([a-z]{2}(?:-[a-z]+)+-\d)_([A-Za-z0-9]+)$/.exec(pool);
  const clientId = env.VITE_COGNITO_CLIENT_ID || '';
  if (!match || !/^[a-zA-Z0-9]+$/.test(clientId))
    throw new Error('Configure the Cognito pool and public app client.');
  const domain = new URL(env.VITE_COGNITO_DOMAIN || '');
  if (
    domain.protocol !== 'https:' ||
    domain.username ||
    domain.password ||
    domain.pathname !== '/' ||
    domain.search ||
    domain.hash
  )
    throw new Error('Cognito domain must be an HTTPS origin.');
  const callback = new URL(env.VITE_COGNITO_REDIRECT_URI || origin + '/auth/callback');
  const logout = new URL(env.VITE_COGNITO_LOGOUT_URI || origin + '/');
  for (const url of [callback, logout]) {
    if (
      url.origin !== origin ||
      url.username ||
      url.password ||
      url.search ||
      url.hash ||
      (url.protocol !== 'https:' && !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname))
    )
      throw new Error(
        'Callback and logout URLs must use this site origin (HTTPS except loopback development).',
      );
  }
  if (callback.pathname !== '/auth/callback' || logout.pathname !== '/')
    throw new Error('Use /auth/callback for the callback and / for logout.');
  const scope = env.VITE_COGNITO_SCOPES || 'openid profile';
  if (!scope.split(/\s+/).includes('openid'))
    throw new Error('Cognito scopes must include openid.');
  const resource = env.VITE_COGNITO_RESOURCE || undefined;
  if (resource) {
    const url = new URL(resource);
    if (url.protocol !== 'https:' || url.username || url.password || url.hash)
      throw new Error('Cognito resource must be an HTTPS URI.');
  }
  return {
    mode,
    authority: `https://cognito-idp.${match[1]}.amazonaws.com${match[1].startsWith('cn-') ? '.cn' : ''}/${pool}`,
    domain: domain.origin,
    clientId,
    redirectUri: callback.href,
    logoutUri: logout.href,
    scope,
    resource,
  };
}

export function createManager(config: CognitoConfig) {
  return new UserManager({
    authority: config.authority,
    client_id: config.clientId,
    redirect_uri: config.redirectUri,
    response_type: 'code',
    scope: config.scope,
    loadUserInfo: false,
    automaticSilentRenew: false,
    requestTimeoutInSeconds: 10,
    staleStateAgeInSeconds: 600,
    userStore: new WebStorageStateStore({ store: new InMemoryWebStorage() }),
    stateStore: new WebStorageStateStore({ store: window.sessionStorage }),
    extraQueryParams: config.resource ? { resource: config.resource } : undefined,
    metadata: {
      issuer: config.authority,
      authorization_endpoint: config.domain + '/oauth2/authorize',
      token_endpoint: config.domain + '/oauth2/token',
      revocation_endpoint: config.domain + '/oauth2/revoke',
      jwks_uri: config.authority + '/.well-known/jwks.json',
    },
  });
}

type Manager = Pick<
  UserManager,
  | 'getUser'
  | 'signinRedirectCallback'
  | 'signinRedirect'
  | 'signinSilent'
  | 'removeUser'
  | 'clearStaleState'
>;
type Snapshot = {
  status: 'loading' | 'ready' | 'signed_out' | 'error';
  principal?: Principal;
  message?: string;
};
export class BrowserAuth {
  private snapshot: Snapshot = { status: 'loading' };
  private listeners = new Set<() => void>();
  private initialization?: Promise<void>;
  private renewal?: Promise<User>;
  private user: User | null = null;
  private timer?: ReturnType<typeof setTimeout>;
  private revision = 0;
  constructor(
    readonly config: AuthConfig,
    private manager?: Manager,
    private http: typeof fetch = (...args) => fetch(...args),
  ) {}
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  getSnapshot = () => this.snapshot;
  getRevision = () => this.revision;
  private publish(snapshot: Snapshot) {
    this.snapshot = snapshot;
    this.listeners.forEach((listener) => listener());
  }
  initialize = () => (this.initialization ??= this.start());
  private async start() {
    const revision = this.revision;
    try {
      let user: User | null = null;
      let returnPath = '/';
      if (this.manager) {
        if (window.location.pathname === '/auth/callback') {
          const url = window.location.href;
          window.history.replaceState({}, '', '/');
          user = await this.manager.signinRedirectCallback(url);
          const state = user.state as { returnPath?: unknown } | undefined;
          if (
            typeof state?.returnPath === 'string' &&
            state.returnPath.startsWith('/') &&
            !state.returnPath.startsWith('//')
          ) {
            const target = new URL(state.returnPath, window.location.origin);
            if (target.origin === window.location.origin && target.pathname !== '/auth/callback')
              returnPath = target.pathname + target.search;
          }
        } else user = await this.manager.getUser();
        await this.manager.clearStaleState();
        if (revision !== this.revision) return;
        if (!user || user.expired) {
          this.invalidate();
          return;
        }
      }
      const response = await this.http(serviceUrl('/api/v1/auth/me'), {
        headers: user ? { Authorization: `Bearer ${user.access_token}` } : {},
        credentials: 'omit',
        cache: 'no-store',
        redirect: 'error',
        signal: AbortSignal.timeout(10000),
      });
      if (!response.ok)
        throw new Error('Could not verify your session with the inspection service.');
      const principal = (await response.json()) as Principal;
      if (
        principal.auth_mode !== this.config.mode ||
        !principal.subject ||
        !principal.owner_id ||
        (user && principal.subject !== user.profile.sub)
      )
        throw new Error('Browser and service authentication settings do not match.');
      if (revision !== this.revision) return;
      if (user) this.accept(user);
      this.publish({ status: 'ready', principal });
      if (returnPath !== '/') window.history.replaceState({}, '', returnPath);
    } catch {
      if (revision !== this.revision) return;
      this.invalidate(
        'Sign-in could not be verified. Check the service connection and authentication settings, then try again.',
      );
    }
  }
  private accept(user: User) {
    if (
      !user.access_token ||
      !user.expires_at ||
      user.expired ||
      (this.user && user.profile.sub !== this.user.profile.sub)
    )
      throw new Error('Invalid or changed session.');
    this.user = user;
    clearTimeout(this.timer);
    this.timer = setTimeout(
      () => {
        if (user.refresh_token) void this.refresh().catch(() => {});
        else this.invalidate('Your session expired. Sign in again.');
      },
      Math.max(1000, ((user.expires_in || 0) - 30) * 1000),
    );
  }
  invalidate = (message?: string) => {
    this.revision++;
    clearTimeout(this.timer);
    this.user = null;
    this.publish({ status: message ? 'error' : 'signed_out', message });
    void this.manager?.removeUser().catch(() => {});
  };
  private refresh(): Promise<User> {
    if (this.renewal) return this.renewal;
    const revision = this.revision;
    this.renewal = (async () => {
      try {
        if (!this.user?.refresh_token || !this.manager) throw new Error('No renewable session.');
        const user = await this.manager.signinSilent();
        if (revision !== this.revision) {
          await this.manager.removeUser();
          throw new Error('Session ended.');
        }
        if (!user) throw new Error('Session renewal failed.');
        this.accept(user);
        return user;
      } catch (error) {
        if (revision === this.revision) this.invalidate('Your session expired. Sign in again.');
        throw error;
      } finally {
        this.renewal = undefined;
      }
    })();
    return this.renewal;
  }
  accessToken = async () => {
    if (this.config.mode === 'local') return null;
    if (this.snapshot.status !== 'ready' || !this.user) throw new Error('Sign in to continue.');
    if ((this.user.expires_in || 0) <= 30) await this.refresh();
    if (!this.user) throw new Error('Sign in to continue.');
    return this.user.access_token;
  };
  login = async () => {
    if (!this.manager) {
      window.location.reload();
      return;
    }
    this.publish({ status: 'loading' });
    try {
      await this.manager.signinRedirect({
        state: { returnPath: window.location.pathname + window.location.search },
        nonce: crypto.randomUUID(),
      });
    } catch {
      this.invalidate('The sign-in page could not be opened. Please try again.');
    }
  };
  logout = async () => {
    const refreshToken = this.user?.refresh_token;
    this.invalidate();
    if (this.config.mode !== 'cognito') return;
    const config = this.config;
    if (refreshToken) {
      await this.http(config.domain + '/oauth2/revoke', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ client_id: config.clientId, token: refreshToken }),
        credentials: 'omit',
        redirect: 'error',
        signal: AbortSignal.timeout(3000),
      }).catch(() => {});
    }
    window.location.assign(
      config.domain +
        '/logout?' +
        new URLSearchParams({ client_id: config.clientId, logout_uri: config.logoutUri }),
    );
  };
}

let configError: string | undefined;
let config: AuthConfig = { mode: 'local' };
let manager: UserManager | undefined;
try {
  config = readAuthConfig(import.meta.env, window.location.origin);
  if (config.mode === 'cognito') manager = createManager(config);
} catch {
  configError = 'Authentication configuration is invalid. Check the browser deployment settings.';
}
export const authConfigurationError = configError;
export const auth = new BrowserAuth(config, manager);
