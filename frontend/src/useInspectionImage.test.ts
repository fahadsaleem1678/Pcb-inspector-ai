import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { protectedResponse } from './api';
import { useInspectionImage } from './useInspectionImage';
vi.mock('./api', () => ({
  protectedResponse: vi.fn(),
  imageUrl: (id: string) => '/api/v1/inspections/' + id + '/image',
  errorMessage: () => 'Image unavailable',
}));
afterEach(() => {
  vi.restoreAllMocks();
  vi.clearAllMocks();
});
it('ignores a late image response after navigation and revokes the displayed blob on unmount', async () => {
  let finish!: (response: Response) => void;
  vi.mocked(protectedResponse)
    .mockReturnValueOnce(
      new Promise((resolve) => {
        finish = resolve;
      }),
    )
    .mockResolvedValueOnce(new Response(new Blob(['second'])));
  const create = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:second');
  const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
  const hook = renderHook(({ id }) => useInspectionImage(id), { initialProps: { id: 'first' } });
  const firstSignal = vi.mocked(protectedResponse).mock.calls[0][1]?.signal;
  hook.rerender({ id: 'second' });
  await waitFor(() => expect(hook.result.current.url).toBe('blob:second'));
  expect(firstSignal?.aborted).toBe(true);
  await act(async () => {
    finish(new Response(new Blob(['first'])));
  });
  expect(create).toHaveBeenCalledTimes(1);
  expect(hook.result.current.url).toBe('blob:second');
  hook.unmount();
  expect(revoke).toHaveBeenCalledWith('blob:second');
});
it('does not reuse a revoked image when the same inspection is reopened', async () => {
  vi.mocked(protectedResponse).mockResolvedValueOnce(new Response(new Blob(['first'])));
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:first');
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
  const hook = renderHook(({ id }) => useInspectionImage(id), {
    initialProps: { id: 'first' as string | null },
  });
  await waitFor(() => expect(hook.result.current.url).toBe('blob:first'));
  hook.rerender({ id: null });
  vi.mocked(protectedResponse).mockReturnValueOnce(new Promise(() => {}));
  hook.rerender({ id: 'first' });
  expect(hook.result.current.url).toBeNull();
  hook.unmount();
});
