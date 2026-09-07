import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from './api';
import { useInspection } from './useInspection';
import type { Inspection, Report } from './api';

const job = (id: string): Inspection => ({
  id,
  status: 'COMPLETED',
  created_at: '2026-09-07T10:00:00Z',
  completed_at: '2026-09-07T10:00:01Z',
  width: 128,
  height: 96,
  attempts: 1,
  model_version: 'demo',
  error_code: null,
  overall_result: 'NOT_EVALUATED',
});
const report = (id: string): Report => ({
  schema_version: '1.0',
  decision_policy_version: 'provisional-1',
  inspection_id: id,
  model_version: 'demo',
  is_demo: true,
  overall_result: 'NOT_EVALUATED',
  inference_time_ms: 1,
  image_width: 128,
  image_height: 96,
  detections: [],
  ignored_detection_count: 0,
  limitations: [],
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe('inspection lifecycle', () => {
  it('discards late results when switching inspections', async () => {
    let resolveFirst!: (value: Inspection) => void;
    vi.spyOn(api, 'inspection').mockImplementation((id) =>
      id === 'first'
        ? new Promise((resolve) => {
            resolveFirst = resolve;
          })
        : Promise.resolve(job(id)),
    );
    vi.spyOn(api, 'report').mockImplementation((id) => Promise.resolve(report(id)));
    const { result, rerender } = renderHook(({ id }) => useInspection(id), {
      initialProps: { id: 'first' },
    });
    rerender({ id: 'second' });
    await waitFor(() => expect(result.current.report?.inspection_id).toBe('second'));
    await act(async () => {
      resolveFirst(job('first'));
    });
    expect(result.current.report?.inspection_id).toBe('second');
  });

  it('stops polling at a terminal failure', async () => {
    vi.useFakeTimers();
    const fetchJob = vi
      .spyOn(api, 'inspection')
      .mockResolvedValue({ ...job('failed'), status: 'FAILED' });
    const fetchReport = vi.spyOn(api, 'report');
    const { result } = renderHook(() => useInspection('failed'));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.job?.status).toBe('FAILED');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(fetchJob).toHaveBeenCalledTimes(1);
    expect(fetchReport).not.toHaveBeenCalled();
  });
});
