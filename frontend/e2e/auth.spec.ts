import { test, expect } from '@playwright/test';
import type { Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { createHash } from 'node:crypto';
const domain = 'https://pcb-test.auth.us-east-1.amazoncognito.com';
const subject = '11111111-1111-4111-8111-111111111111';
const inspection = '22222222-2222-4222-8222-222222222222';
function jwt(payload: object) {
  return [
    Buffer.from('{"alg":"RS256","typ":"JWT"}').toString('base64url'),
    Buffer.from(JSON.stringify(payload)).toString('base64url'),
    'mock-signature',
  ].join('.');
}
async function provider(
  page: Page,
  options: {
    rejectState?: boolean;
    refreshFails?: boolean;
    expireSoon?: boolean;
    rejectUpload?: boolean;
  } = {},
) {
  let nonce = '';
  let challenge = '';
  let exchanges = 0;
  let refreshes = 0;
  let uploads = 0;
  const resources: string[] = [];
  await page.route(domain + '/**', async (route) => {
    const url = new URL(route.request().url());
    if (route.request().method() === 'OPTIONS') {
      await route.fulfill({
        status: 204,
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Headers': 'content-type',
          'Access-Control-Allow-Methods': 'POST',
        },
      });
      return;
    }
    if (url.pathname === '/oauth2/authorize') {
      expect(url.searchParams.get('response_type')).toBe('code');
      expect(url.searchParams.get('code_challenge_method')).toBe('S256');
      expect(url.searchParams.has('client_secret')).toBe(false);
      nonce = url.searchParams.get('nonce')!;
      challenge = url.searchParams.get('code_challenge')!;
      expect(nonce).toBeTruthy();
      expect(challenge).toBeTruthy();
      const callback = new URL(url.searchParams.get('redirect_uri')!);
      callback.searchParams.set('code', 'test-authorization-code');
      callback.searchParams.set(
        'state',
        options.rejectState ? 'invalid-state' : url.searchParams.get('state')!,
      );
      await route.fulfill({ status: 302, headers: { location: callback.href }, body: '' });
      return;
    }
    if (url.pathname === '/oauth2/token') {
      const data = new URLSearchParams(route.request().postData()!);
      expect(data.get('client_id')).toBe('publicclient');
      expect(data.has('client_secret')).toBe(false);
      if (data.get('grant_type') === 'authorization_code') {
        exchanges++;
        expect(data.get('code')).toBe('test-authorization-code');
        expect(createHash('sha256').update(data.get('code_verifier')!).digest('base64url')).toBe(
          challenge,
        );
      } else {
        refreshes++;
        expect(data.get('grant_type')).toBe('refresh_token');
        expect(data.get('refresh_token')).toBe('test-refresh-token');
        if (options.refreshFails) {
          await route.fulfill({
            status: 400,
            headers: { 'Access-Control-Allow-Origin': '*' },
            json: { error: 'invalid_grant' },
          });
          return;
        }
      }
      const now = Math.floor(Date.now() / 1000);
      await route.fulfill({
        headers: { 'Access-Control-Allow-Origin': '*' },
        json: {
          token_type: 'Bearer',
          access_token: refreshes ? 'test-renewed-access-token' : 'test-access-token',
          refresh_token: 'test-refresh-token',
          expires_in: options.expireSoon && !refreshes ? 32 : 3600,
          scope: 'openid profile',
          id_token: jwt({
            sub: subject,
            nonce,
            iss: 'https://cognito-idp.us-east-1.amazonaws.com/us-east-1_TestPool',
            aud: 'publicclient',
            iat: now,
            exp: now + 3600,
          }),
        },
      });
      return;
    }
    if (url.pathname === '/oauth2/revoke') {
      await route.abort();
      return;
    }
    if (url.pathname === '/logout') {
      expect(url.searchParams.get('client_id')).toBe('publicclient');
      await route.fulfill({
        status: 302,
        headers: { location: url.searchParams.get('logout_uri')! },
        body: '',
      });
      return;
    }
    throw new Error('Unexpected provider endpoint ' + url.pathname);
  });
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    expect(request.headers().authorization).toMatch(/^Bearer test-(renewed-)?access-token$/);
    expect(url.search).not.toContain('token');
    resources.push(url.pathname);
    if (url.pathname === '/api/v1/auth/me') {
      await route.fulfill({
        json: { subject, owner_id: 'cognito:test:' + subject, auth_mode: 'cognito', scopes: [] },
      });
      return;
    }
    if (url.pathname.endsWith('/upload')) {
      uploads++;
      await route.fulfill({
        status: options.rejectUpload ? 401 : 500,
        json: { detail: 'Session rejected' },
      });
      return;
    }
    if (url.pathname.endsWith('/image')) {
      await route.fulfill({
        contentType: 'image/png',
        body: Buffer.from(
          'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aV9sAAAAASUVORK5CYII=',
          'base64',
        ),
      });
      return;
    }
    if (url.pathname.endsWith('/report') || url.pathname.endsWith('/results')) {
      await route.fulfill({
        json: {
          inspection_id: inspection,
          is_demo: true,
          overall_result: 'NOT_EVALUATED',
          model_version: 'demo-no-model-0.1.0',
          detections: [],
          inference_time_ms: 1,
        },
      });
      return;
    }
    if (url.pathname.endsWith(inspection)) {
      await route.fulfill({
        json: {
          id: inspection,
          status: 'COMPLETED',
          created_at: '2026-09-13T00:00:00Z',
          width: 1,
          height: 1,
          filename: 'test.png',
          error_code: null,
        },
      });
      return;
    }
    await route.fulfill({ json: { items: [], total: 0, limit: 10, offset: 0 } });
  });
  return {
    resources,
    exchanges: () => exchanges,
    refreshes: () => refreshes,
    uploads: () => uploads,
  };
}
async function login(page: Page, path = '/') {
  await page.goto(path);
  await page.getByRole('button', { name: 'Sign in or create an account' }).click();
}

test('PKCE login preserves the selected inspection and protects images/downloads; logout clears tokens even if revocation fails', async ({
  page,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const mock = await provider(page);
  await login(page, '/?inspection=' + inspection);
  await expect(page.getByRole('heading', { name: 'Board not evaluated' })).toBeVisible();
  await expect(page.getByRole('img', { name: 'PCB image submitted for inspection' })).toBeVisible();
  expect(new URL(page.url()).searchParams.get('inspection')).toBe(inspection);
  expect(page.url()).not.toContain('code=');
  expect(mock.exchanges()).toBe(1);
  const stored = await page.evaluate(() =>
    JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }),
  );
  expect(stored).not.toContain('test-access-token');
  expect(stored).not.toContain('test-refresh-token');
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download JSON report' }).click();
  expect((await downloadPromise).suggestedFilename()).toBe('inspection-' + inspection + '.json');
  expect(mock.resources).toContain('/api/v1/inspections/' + inspection + '/image');
  expect(mock.resources).toContain('/api/v1/inspections/' + inspection + '/report');
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Sign in or create an account' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Board not evaluated' })).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('invalid callback state fails before token exchange and cleans the URL', async ({ page }) => {
  const mock = await provider(page, { rejectState: true });
  await login(page);
  await expect(page.getByRole('alert')).toContainText('Sign-in could not be verified');
  expect(mock.exchanges()).toBe(0);
  expect(new URL(page.url()).search).toBe('');
  expect(mock.resources).toHaveLength(0);
});

test('session renewal uses the refresh grant and keeps the workspace open', async ({ page }) => {
  const mock = await provider(page, { expireSoon: true });
  await login(page);
  await expect(page.getByRole('button', { name: 'Sign out', exact: true })).toBeVisible();
  await expect.poll(mock.refreshes).toBe(1);
  await page.getByRole('button', { name: 'Refresh history' }).click();
  await expect(page.getByRole('button', { name: 'Sign out', exact: true })).toBeVisible();
});

test('refresh rejection closes the workspace', async ({ page }) => {
  const mock = await provider(page, { expireSoon: true, refreshFails: true });
  await login(page);
  await expect(page.getByRole('button', { name: 'Sign out', exact: true })).toBeVisible();
  await expect(page.getByRole('alert')).toContainText('session expired');
  expect(mock.refreshes()).toBe(1);
  await expect(page.getByLabel('Choose PCB image')).toHaveCount(0);
});

test('401 closes the workspace without replaying an upload', async ({ page }) => {
  const mock = await provider(page, { rejectUpload: true });
  await login(page);
  await page
    .getByLabel('Choose PCB image')
    .setInputFiles({ name: 'board.png', mimeType: 'image/png', buffer: Buffer.from('test-only') });
  await page.getByRole('button', { name: 'Run demo inspection' }).click();
  await expect(page.getByRole('alert')).toContainText('session is no longer valid');
  expect(mock.uploads()).toBe(1);
});
