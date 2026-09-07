import { useEffect, useState } from 'react';
import {
  ArrowClockwise,
  ArrowLeft,
  ArrowRight,
  ClockCounterClockwise,
} from '@phosphor-icons/react';
import { api, errorMessage, imageUrl } from '../api';
import type { History } from '../api';

export function HistoryPanel({
  selectedId,
  onSelect,
  refresh,
  busy,
}: {
  selectedId: string | null;
  onSelect: (id: string) => void;
  refresh: number;
  busy: boolean;
}) {
  const [offset, setOffset] = useState(0);
  const [reload, setReload] = useState(0);
  const [state, setState] = useState<{
    offset: number;
    data: History | null;
    error: string | null;
  }>({
    offset: 0,
    data: null,
    error: null,
  });
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const data = await api.history(offset, controller.signal);
        if (controller.signal.aborted) return;
        setState({ offset, data, error: null });
        if (data.items.some((job) => ['QUEUED', 'PROCESSING'].includes(job.status)))
          timer = setTimeout(load, 3000);
      } catch (error) {
        if (!controller.signal.aborted)
          setState({ offset, data: null, error: errorMessage(error) });
      }
    }
    void load();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [offset, refresh, reload]);
  const page = state.offset === offset ? state.data : null;
  return (
    <section className="history-panel" aria-labelledby="history-title">
      <div className="history-header">
        <div>
          <span className="eyebrow">YOUR WORKSPACE</span>
          <h2 id="history-title">Inspection history</h2>
        </div>
        <button className="button quiet" onClick={() => setReload((value) => value + 1)}>
          <ArrowClockwise size={17} aria-hidden /> Refresh history
        </button>
      </div>
      {state.error && (
        <div role="alert" className="error-message">
          {state.error}
        </div>
      )}
      {!page && !state.error && (
        <p role="status" className="history-placeholder">
          Loading inspections…
        </p>
      )}
      {page?.items.length === 0 && (
        <div className="history-placeholder">
          <ClockCounterClockwise size={26} aria-hidden />
          <h3>{offset ? 'No more inspections' : 'Every inspection starts a record.'}</h3>
          <p>
            {offset
              ? 'Go back to the previous page.'
              : 'Upload your first board image. Your saved inspections will appear here.'}
          </p>
        </div>
      )}
      {page && page.items.length > 0 && (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th scope="col">Inspection</th>
                <th scope="col">Submitted</th>
                <th scope="col">Image</th>
                <th scope="col">Processing</th>
                <th scope="col">Assessment</th>
                <th scope="col">
                  <span className="sr-only">Open</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {page.items.map((job) => (
                <tr key={job.id} className={job.id === selectedId ? 'active-row' : ''}>
                  <td>
                    <div className="history-identity">
                      <img src={imageUrl(job.id)} alt="" loading="lazy" />
                      <span className="mono">{job.id.slice(0, 8)}</span>
                    </div>
                  </td>
                  <td>
                    {new Date(job.created_at).toLocaleString(undefined, {
                      month: 'short',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </td>
                  <td className="mono">
                    {job.width} × {job.height}
                  </td>
                  <td>
                    <span className={`status-badge status-${job.status.toLowerCase()}`}>
                      {job.status.toLowerCase()}
                    </span>
                  </td>
                  <td>
                    {job.overall_result === 'NOT_EVALUATED'
                      ? 'Not evaluated'
                      : job.overall_result === 'REVIEW_REQUIRED'
                        ? 'Review required'
                        : job.overall_result === 'NO_VISIBLE_DEFECTS_DETECTED'
                          ? 'No visible defects'
                          : job.status.toLowerCase()}
                  </td>
                  <td>
                    <button
                      className="icon-button"
                      aria-label={`Open inspection ${job.id.slice(0, 8)}`}
                      disabled={busy}
                      onClick={() => onSelect(job.id)}
                    >
                      <ArrowRight size={19} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="pagination">
        <span>
          {page && page.items.length > 0
            ? `Showing ${offset + 1}–${offset + page.items.length}`
            : 'Saved locally'}
        </span>
        <div>
          <button
            className="button quiet"
            disabled={offset === 0}
            onClick={() => setOffset((value) => Math.max(0, value - 10))}
          >
            <ArrowLeft size={16} aria-hidden /> Previous
          </button>
          <button
            className="button quiet"
            disabled={!page || page.items.length < 10}
            onClick={() => setOffset((value) => value + 10)}
          >
            Next <ArrowRight size={16} aria-hidden />
          </button>
        </div>
      </div>
    </section>
  );
}
