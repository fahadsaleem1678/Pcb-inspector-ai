import { ArrowDown, Clock, Info, WarningCircle } from '@phosphor-icons/react';
import type { Inspection, Report } from '../api';
import { reportUrl } from '../api';

export function ReportPanel({
  job,
  report,
  error,
  onRetry,
  selected,
  onSelect,
}: {
  job: Inspection | null;
  report: Report | null;
  error: string | null;
  onRetry: () => void;
  selected: number | null;
  onSelect: (index: number | null) => void;
}) {
  const pending = job?.status === 'QUEUED' || job?.status === 'PROCESSING';
  return (
    <aside className="report-panel" aria-label="Inspection report">
      <div className="panel-heading">
        <h2>Inspection details</h2>
        <span className="eyebrow">REPORT</span>
      </div>
      {error && (
        <div className="error-message" role="alert">
          <p>{error}</p>
          <button className="text-button" onClick={onRetry}>
            Retry connection
          </button>
        </div>
      )}
      {!job && !error && (
        <div className="report-empty">
          <Info size={28} weight="light" aria-hidden />
          <h3>A clear record of your inspection.</h3>
          <p>Processing status, image details, and your report will appear here.</p>
        </div>
      )}
      {pending && (
        <div className="result-notice" role="status">
          <Clock size={24} aria-hidden />
          <h3>{job.status === 'QUEUED' ? 'Waiting for the worker' : 'Processing your image'}</h3>
          <p>
            {job.status === 'QUEUED'
              ? 'Your image is saved. This page updates automatically when processing starts.'
              : 'Preparing the inspection report. You can return to this inspection from history.'}
          </p>
        </div>
      )}
      {job?.status === 'FAILED' && (
        <div className="error-message" role="alert">
          <WarningCircle size={24} aria-hidden />
          <h3>Processing could not finish</h3>
          <p>The worker exhausted its retries. No inspection result is available.</p>
          <p className="mono">{job.error_code}</p>
        </div>
      )}
      {job?.status === 'COMPLETED' && !report && !error && (
        <p role="status">Loading your report…</p>
      )}
      {report && (
        <>
          <div
            className={report.is_demo ? 'result-notice' : 'result-notice evaluated'}
            role="status"
          >
            <Info size={24} aria-hidden />
            <p className="eyebrow">{report.is_demo ? 'DEMO REPORT' : 'VISUAL FINDINGS'}</p>
            <h3>
              {report.is_demo || report.overall_result === 'NOT_EVALUATED'
                ? 'Board not evaluated'
                : report.overall_result === 'REVIEW_REQUIRED'
                  ? 'Review required'
                  : 'No visible defects detected'}
            </h3>
            <p>
              {report.is_demo
                ? 'The workflow completed successfully. No trained detector ran, so this is not a defect assessment.'
                : 'Review the visible findings below. This result does not certify electrical or functional correctness.'}
            </p>
          </div>
          {!report.is_demo && (
            <section className="findings" aria-label="Detected defects">
              <h3>
                Findings <span>{report.detections.length}</span>
              </h3>
              {report.detections.length === 0 && (
                <p>No findings met the current reporting thresholds.</p>
              )}
              {report.detections.map((finding, index) => (
                <button
                  key={index}
                  className={selected === index ? 'finding selected' : 'finding'}
                  aria-pressed={selected === index}
                  onClick={() => onSelect(selected === index ? null : index)}
                >
                  <span className="finding-number">{index + 1}</span>
                  <span>
                    <strong>{finding.defect_type.replaceAll('_', ' ')}</strong>
                    <small>
                      {finding.severity} · {finding.confidence_band} confidence
                    </small>
                  </span>
                  <span className="mono">{(finding.confidence * 100).toFixed(1)}%</span>
                </button>
              ))}
            </section>
          )}
        </>
      )}
      {job && (
        <dl className="metadata">
          <div>
            <dt>Job status</dt>
            <dd>{job.status.toLowerCase()}</dd>
          </div>
          <div>
            <dt>Inspection ID</dt>
            <dd className="mono full-id">{job.id}</dd>
          </div>
          <div>
            <dt>Submitted</dt>
            <dd>{new Date(job.created_at).toLocaleString()}</dd>
          </div>
          <div>
            <dt>Image size</dt>
            <dd>
              {job.width} × {job.height} px
            </dd>
          </div>
          {report && (
            <>
              <div>
                <dt>Model version</dt>
                <dd className="mono">{report.model_version}</dd>
              </div>
              <div>
                <dt>Processing time</dt>
                <dd>{report.inference_time_ms} ms</dd>
              </div>
            </>
          )}
        </dl>
      )}
      {report && (
        <a className="button secondary download" href={reportUrl(report.inspection_id)} download>
          <ArrowDown size={18} aria-hidden /> Download JSON report
        </a>
      )}
      <p className="scope-note">
        AI-assisted visual inspection only. No electrical, functional, or manufacturing
        certification.
      </p>
    </aside>
  );
}
