import { useState } from 'react';
import { ArrowsOut, Minus, Plus, Scan } from '@phosphor-icons/react';
import type { Finding } from '../api';

export function ImageViewer({
  src,
  width,
  height,
  findings = [],
  selected,
  onSelect,
}: {
  src: string;
  width?: number;
  height?: number;
  findings?: Finding[];
  selected: number | null;
  onSelect: (index: number | null) => void;
}) {
  const [zoom, setZoom] = useState(1);
  const [showBoxes, setShowBoxes] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  return (
    <section className="viewer" aria-label="Board image viewer">
      <div className="viewer-toolbar">
        <span>
          <Scan size={17} aria-hidden /> Board image
        </span>
        <div className="viewer-actions">
          <label className="box-toggle">
            <input
              type="checkbox"
              checked={showBoxes}
              onChange={(event) => setShowBoxes(event.target.checked)}
            />{' '}
            Show regions
          </label>
          <button
            className="icon-button"
            aria-label="Zoom out"
            disabled={zoom <= 1}
            onClick={() => setZoom((value) => Math.max(1, value - 0.25))}
          >
            <Minus />
          </button>
          <output aria-label="Zoom level">{Math.round(zoom * 100)}%</output>
          <button
            className="icon-button"
            aria-label="Zoom in"
            disabled={zoom >= 3}
            onClick={() => setZoom((value) => Math.min(3, value + 0.25))}
          >
            <Plus />
          </button>
          <button className="icon-button" aria-label="Fit image" onClick={() => setZoom(1)}>
            <ArrowsOut />
          </button>
        </div>
      </div>
      <div className="viewer-scroll" tabIndex={0} aria-label="Scrollable board image">
        {loadFailed ? (
          <p role="alert" className="viewer-error">
            The image could not be loaded. Reopen this inspection to try again.
          </p>
        ) : (
          <div className="image-stage" style={{ width: `${zoom * 100}%` }}>
            <div className="image-coordinate-space">
              <img
                src={src}
                alt="PCB image submitted for inspection"
                onError={() => setLoadFailed(true)}
              />
              {showBoxes && width && height && findings.length > 0 && (
                <svg
                  className="detection-overlay"
                  viewBox={`0 0 ${width} ${height}`}
                  aria-label="Detected regions"
                  role="group"
                >
                  {findings.map((finding, index) => (
                    <g
                      key={index}
                      role="button"
                      tabIndex={0}
                      aria-label={`Region ${index + 1}: ${finding.defect_type.replaceAll('_', ' ')}`}
                      aria-pressed={selected === index}
                      onClick={() => onSelect(selected === index ? null : index)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault();
                          onSelect(selected === index ? null : index);
                        }
                      }}
                    >
                      <rect
                        x={finding.bbox.x1}
                        y={finding.bbox.y1}
                        width={finding.bbox.x2 - finding.bbox.x1}
                        height={finding.bbox.y2 - finding.bbox.y1}
                        vectorEffect="non-scaling-stroke"
                        className={selected === index ? 'selected-region' : ''}
                      />
                    </g>
                  ))}
                </svg>
              )}
            </div>
          </div>
        )}
      </div>
      <div className="viewer-caption">
        <span>Visible surfaces only</span>
        <span>{width && height ? `${width} × ${height} px` : 'Local preview'}</span>
      </div>
    </section>
  );
}
