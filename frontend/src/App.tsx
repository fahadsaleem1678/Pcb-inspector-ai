import { useEffect, useRef, useState } from 'react';
import {
  ArrowRight,
  Circuitry,
  FileImage,
  Info,
  Plus,
  UploadSimple,
  X,
} from '@phosphor-icons/react';
import { api, errorMessage } from './api';
import type { Principal } from './auth';
import { useInspectionImage } from './useInspectionImage';
import { useInspection } from './useInspection';
import { ImageViewer } from './components/ImageViewer';
import { ReportPanel } from './components/ReportPanel';
import { HistoryPanel } from './components/HistoryPanel';

function selectedFromUrl() {
  const id = new URLSearchParams(window.location.search).get('inspection');
  return id && /^[a-f0-9-]{36}$/i.test(id) ? id : null;
}

export default function App({
  principal,
  onLogout,
}: {
  principal?: Principal;
  onLogout?: () => Promise<void>;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(selectedFromUrl);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [historyRefresh, setHistoryRefresh] = useState(0);
  const [selectedFinding, setSelectedFinding] = useState<number | null>(null);
  const submitLock = useRef(false);
  const input = useRef<HTMLInputElement>(null);
  const { job, report, error, retry } = useInspection(selectedId);

  useEffect(() => {
    if (!file) {
      setPreview(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  useEffect(() => {
    const update = () => {
      setSelectedId(selectedFromUrl());
      setFile(null);
      setUploadError(null);
      setSelectedFinding(null);
    };
    window.addEventListener('popstate', update);
    return () => window.removeEventListener('popstate', update);
  }, []);
  useEffect(() => {
    if (job?.status === 'COMPLETED' || job?.status === 'FAILED')
      setHistoryRefresh((value) => value + 1);
  }, [job?.id, job?.status]);

  function navigate(id: string | null) {
    const url = new URL(window.location.href);
    if (id) url.searchParams.set('inspection', id);
    else url.searchParams.delete('inspection');
    window.history.pushState({}, '', url);
    setSelectedId(id);
    setFile(null);
    setUploadError(null);
    setSelectedFinding(null);
  }
  function chooseFile(candidate?: File) {
    if (!candidate || submitLock.current) return;
    if (
      !['image/png', 'image/jpeg'].includes(candidate.type) &&
      !/\.(jpe?g|png)$/i.test(candidate.name)
    ) {
      setUploadError('Choose a JPEG or PNG image.');
      return;
    }
    if (candidate.size > 10 * 1024 * 1024) {
      setUploadError('This file is larger than 10 MB. Choose a smaller image.');
      return;
    }
    if (candidate.size === 0) {
      setUploadError('This file is empty. Choose another image.');
      return;
    }
    navigate(null);
    setFile(candidate);
  }
  async function submit() {
    if (!file || submitLock.current) return;
    submitLock.current = true;
    setUploading(true);
    setUploadError(null);
    try {
      const response = await api.upload(file);
      navigate(response.inspection_id);
      setHistoryRefresh((value) => value + 1);
    } catch (error) {
      setUploadError(errorMessage(error));
      setHistoryRefresh((value) => value + 1);
    } finally {
      submitLock.current = false;
      setUploading(false);
    }
  }
  const image = useInspectionImage(selectedId);
  const source = selectedId ? image.url : preview;
  return (
    <>
      <a href="#main" className="skip-link">
        Skip to inspection workspace
      </a>
      <header className="app-header">
        <div className="header-inner">
          <a
            className="brand"
            href="/"
            onClick={(event) => {
              event.preventDefault();
              if (!uploading) navigate(null);
            }}
          >
            <span className="brand-mark">
              <Circuitry size={25} weight="regular" aria-hidden />
            </span>
            <span>
              PCB <span className="brand-light">Inspector AI</span>
            </span>
          </a>
          <div className="workspace-label">
            {principal?.auth_mode === 'cognito' ? 'YOUR WORKSPACE' : 'LOCAL WORKSPACE'}
            {onLogout ? (
              <button className="text-button" onClick={() => void onLogout()}>
                Sign out
              </button>
            ) : (
              <span className="avatar">L</span>
            )}
          </div>
        </div>
      </header>
      <main id="main">
        <div className="page-heading">
          <div>
            <p className="eyebrow">VISUAL INSPECTION / WORKSPACE</p>
            <h1>See the details. Keep the record.</h1>
            <p>Upload a board image, follow processing, and review your inspection.</p>
          </div>
          <button
            className="button secondary"
            disabled={uploading}
            onClick={() => {
              navigate(null);
            }}
          >
            <Plus size={18} aria-hidden /> New inspection
          </button>
        </div>
        <div className="demo-banner">
          <Info size={20} aria-hidden />
          <p>
            <strong>Demo mode</strong>
            <span>
              Explore the inspection workflow. No trained model is connected; boards are not
              evaluated for defects.
            </span>
          </p>
          <span className="demo-tag">WORKFLOW PREVIEW</span>
        </div>
        <div className="inspection-layout">
          <div className="image-column">
            <div className="section-heading">
              <h2>{selectedId ? 'Selected inspection' : 'New inspection'}</h2>
              <span className="eyebrow">
                {selectedId ? selectedId.slice(0, 8).toUpperCase() : '01 / UPLOAD'}
              </span>
            </div>
            <input
              ref={input}
              type="file"
              accept="image/jpeg,image/png"
              className="sr-only"
              id="board-file"
              tabIndex={-1}
              aria-label="Choose PCB image"
              disabled={uploading}
              onChange={(event) => {
                chooseFile(event.target.files?.[0]);
                event.target.value = '';
              }}
            />
            {image.error && !error && (
              <p className="error-message" role="alert">
                {image.error}
              </p>
            )}
            {selectedId && !source && !image.error && <p role="status">Loading board image…</p>}
            {source ? (
              <ImageViewer
                key={source}
                src={source}
                width={job?.width}
                height={job?.height}
                findings={report?.is_demo ? [] : report?.detections}
                selected={selectedFinding}
                onSelect={setSelectedFinding}
              />
            ) : selectedId ? null : (
              <div
                className={dragging ? 'drop-zone dragging' : 'drop-zone'}
                onDragOver={(event) => {
                  event.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={(event) => {
                  event.preventDefault();
                  setDragging(false);
                  if (event.dataTransfer.files.length > 1)
                    setUploadError('Choose one board image at a time.');
                  else chooseFile(event.dataTransfer.files[0]);
                }}
              >
                <div className="drop-corners" aria-hidden>
                  <span />
                  <span />
                  <span />
                  <span />
                </div>
                <div className="upload-symbol">
                  <UploadSimple size={32} weight="light" aria-hidden />
                </div>
                <h3>Your board, in focus.</h3>
                <p>Drop a PCB image here, or choose a file to get started.</p>
                <button className="button primary" onClick={() => input.current?.click()}>
                  <Plus size={18} aria-hidden /> Choose image
                </button>
                <span className="file-hint">JPEG or PNG · up to 10 MB · at least 64 × 64 px</span>
              </div>
            )}
            {file && !selectedId && (
              <div className="upload-review">
                <div className="file-summary">
                  <FileImage size={23} aria-hidden />
                  <span>
                    <strong>{file.name}</strong>
                    <small>{(file.size / 1024).toFixed(0)} KB · ready to upload</small>
                  </span>
                  <button
                    className="icon-button"
                    aria-label="Remove selected image"
                    disabled={uploading}
                    onClick={() => setFile(null)}
                  >
                    <X size={18} />
                  </button>
                </div>
                <button
                  className="button primary run-button"
                  disabled={uploading}
                  onClick={() => void submit()}
                >
                  {uploading ? 'Uploading image…' : 'Run demo inspection'}
                  <ArrowRight size={18} aria-hidden />
                </button>
              </div>
            )}
            {uploadError && (
              <div role="alert" className="error-message">
                {uploadError}
              </div>
            )}
            {selectedId && !job && !error && <p role="status">Loading inspection…</p>}
            <div className="workflow-note">
              <span className="note-number">01</span>
              <span>Upload image</span>
              <ArrowRight aria-hidden />
              <span className="note-number">02</span>
              <span>Follow processing</span>
              <ArrowRight aria-hidden />
              <span className="note-number">03</span>
              <span>Review report</span>
            </div>
          </div>
          <ReportPanel
            job={job}
            report={report}
            error={error}
            onRetry={retry}
            selected={selectedFinding}
            onSelect={setSelectedFinding}
          />
        </div>
        <HistoryPanel
          selectedId={selectedId}
          onSelect={navigate}
          refresh={historyRefresh}
          busy={uploading}
        />
        <footer className="app-footer">
          <span>PCB Inspector AI</span>
          <span>Visible details. Human judgment.</span>
          <span>Local development · v0.2</span>
        </footer>
      </main>
    </>
  );
}
