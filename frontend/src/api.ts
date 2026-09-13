import { auth } from './auth';
import type { components } from './generated/api';
export type Inspection = components['schemas']['InspectionSummary'];
export type Report = components['schemas']['Report'];
export type Finding = components['schemas']['Finding'];
export type History = components['schemas']['History'];

export class ApiError extends Error {
  constructor(
    message: string,
    public status = 0,
  ) {
    super(message);
  }
}

export async function protectedResponse(path: string, init: RequestInit = {}): Promise<Response> {
  if (
    !path.startsWith('/api/v1/') ||
    new URL(path, window.location.origin).origin !== window.location.origin
  )
    throw new ApiError('Invalid service URL.');
  const revision = auth.getRevision();
  const token = await auth.accessToken();
  if (auth.getRevision() !== revision) throw new ApiError('This session has ended.');
  const headers = new Headers(init.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const timeout = AbortSignal.timeout(init.method === 'POST' ? 30000 : 10000);
  const signal = init.signal ? AbortSignal.any([init.signal, timeout]) : timeout;
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      signal,
      headers,
      credentials: 'omit',
      cache: 'no-store',
      redirect: 'error',
    });
  } catch (error) {
    if (init.signal?.aborted) throw error;
    throw new ApiError(
      init.method === 'POST'
        ? 'The upload response was not received. Refresh history before submitting again.'
        : 'Cannot reach the inspection service. Check the connection and try again.',
    );
  }
  if (auth.getRevision() !== revision) throw new ApiError('This session has ended.');
  if (response.status === 401 && auth.config.mode === 'cognito')
    auth.invalidate('Your session is no longer valid. Sign in again.');
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail = body && typeof body === 'object' && 'detail' in body ? body.detail : null;
    throw new ApiError(
      typeof detail === 'string'
        ? detail
        : response.status === 404
          ? 'This inspection could not be found.'
          : 'The service could not complete the request. Please try again.',
      response.status,
    );
  }
  return response;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  return (await protectedResponse(path, init)).json() as Promise<T>;
}

export const api = {
  history: (offset: number, signal?: AbortSignal) =>
    request<History>(`/api/v1/inspections?limit=10&offset=${offset}`, { signal }),
  inspection: (id: string, signal?: AbortSignal) =>
    request<Inspection>(`/api/v1/inspections/${encodeURIComponent(id)}`, { signal }),
  report: (id: string, signal?: AbortSignal) =>
    request<Report>(`/api/v1/inspections/${encodeURIComponent(id)}/results`, { signal }),
  upload: (file: File) => {
    const data = new FormData();
    data.append('file', file);
    return request<components['schemas']['Submission']>('/api/v1/inspections/upload', {
      method: 'POST',
      body: data,
    });
  },
};
export const imageUrl = (id: string) => `/api/v1/inspections/${encodeURIComponent(id)}/image`;
export const reportUrl = (id: string) => `/api/v1/inspections/${encodeURIComponent(id)}/report`;
export const errorMessage = (error: unknown) =>
  error instanceof Error ? error.message : 'Something went wrong.';
