import { useEffect, useState } from 'react';
import { api, ApiError, errorMessage } from './api';
import type { Inspection, Report } from './api';

type InspectionState = {
  id: string | null;
  job: Inspection | null;
  report: Report | null;
  error: string | null;
};

export function useInspection(id: string | null) {
  const [state, setState] = useState<InspectionState>({
    id: null,
    job: null,
    report: null,
    error: null,
  });
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!id) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let failures = 0;
    async function poll() {
      try {
        const job = await api.inspection(id!, controller.signal);
        if (controller.signal.aborted) return;
        setState({ id, job, report: null, error: null });
        if (job.status === 'COMPLETED') {
          const report = await api.report(id!, controller.signal);
          if (!controller.signal.aborted) setState({ id, job, report, error: null });
          return;
        }
        if (job.status === 'FAILED') return;
        failures = 0;
        timer = setTimeout(poll, 1000);
      } catch (error) {
        if (controller.signal.aborted) return;
        setState((previous) => ({
          id,
          job: previous.id === id ? previous.job : null,
          report: null,
          error: errorMessage(error),
        }));
        if (error instanceof ApiError && [400, 401, 403, 404, 422].includes(error.status)) return;
        timer = setTimeout(poll, Math.min(1000 * 2 ** ++failures, 15000));
      }
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [id, retry]);
  const visible = state.id === id ? state : { job: null, report: null, error: null };
  return { ...visible, retry: () => setRetry((value) => value + 1) };
}
