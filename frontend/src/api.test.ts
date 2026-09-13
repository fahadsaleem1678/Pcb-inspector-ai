import { afterEach, expect, it, vi } from 'vitest';
const session = vi.hoisted(() => ({
  config: { mode: 'cognito' },
  accessToken: vi.fn().mockResolvedValue('access-token'),
  getRevision: vi.fn().mockReturnValue(0),
  invalidate: vi.fn(),
}));
vi.mock('./auth', () => ({ auth: session }));
import { api, imageUrl, protectedResponse, reportUrl } from './api';
afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  session.getRevision.mockReturnValue(0);
});
it('uses bearer headers for image and report delivery without URL credentials', async () => {
  const http = vi.fn().mockResolvedValue(new Response('{}'));
  vi.stubGlobal('fetch', http);
  await protectedResponse(imageUrl('board'));
  await protectedResponse(reportUrl('board'));
  for (const [url, init] of http.mock.calls) {
    expect(url).not.toContain('token');
    expect(init.headers.get('Authorization')).toBe('Bearer access-token');
    expect(init.credentials).toBe('omit');
    expect(init.redirect).toBe('error');
  }
});
it('invalidates a 401 once and never retries an upload', async () => {
  const http = vi.fn().mockResolvedValue(new Response('{}', { status: 401 }));
  vi.stubGlobal('fetch', http);
  await expect(api.upload(new File(['board'], 'board.png'))).rejects.toMatchObject({ status: 401 });
  expect(http).toHaveBeenCalledTimes(1);
  expect(session.invalidate).toHaveBeenCalledTimes(1);
});
it('does not log out for forbidden resources', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 403 })));
  await expect(api.history(0)).rejects.toMatchObject({ status: 403 });
  expect(session.invalidate).not.toHaveBeenCalled();
});
it('rejects results from an earlier session', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(() => {
      session.getRevision.mockReturnValue(1);
      return new Response('{}');
    }),
  );
  await expect(api.history(0)).rejects.toThrow();
});
it('never sends credentials to another origin', async () => {
  const http = vi.fn();
  vi.stubGlobal('fetch', http);
  await expect(protectedResponse('https://other.example/api/v1/inspections')).rejects.toThrow(
    'Invalid service URL',
  );
  expect(http).not.toHaveBeenCalled();
});
