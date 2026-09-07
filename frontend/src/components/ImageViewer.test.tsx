import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ImageViewer } from './ImageViewer';

describe('coordinate overlays', () => {
  it('uses image coordinates and preserves the overlay through zoom and keyboard selection', () => {
    const onSelect = vi.fn();
    const { container } = render(
      <ImageViewer
        src="/board.png"
        width={640}
        height={400}
        findings={[
          {
            defect_type: 'solder_bridge',
            confidence: 0.94,
            severity: 'critical',
            confidence_band: 'high',
            bbox: { x1: 200, y1: 150, x2: 260, y2: 180 },
          },
        ]}
        selected={null}
        onSelect={onSelect}
      />,
    );
    expect(container.querySelector('.detection-overlay')).toHaveAttribute('viewBox', '0 0 640 400');
    expect(container.querySelector('rect')).toHaveAttribute('width', '60');
    expect(container.querySelector('rect')).toHaveAttribute('height', '30');
    fireEvent.keyDown(screen.getByRole('button', { name: 'Region 1: solder bridge' }), {
      key: 'Enter',
    });
    expect(onSelect).toHaveBeenCalledWith(0);
    fireEvent.click(screen.getByRole('button', { name: 'Zoom in' }));
    expect(screen.getByLabelText('Zoom level')).toHaveTextContent('125%');
    expect(container.querySelector('.image-stage')).toHaveStyle({ width: '125%' });
    fireEvent.click(screen.getByLabelText('Show regions'));
    expect(container.querySelector('.detection-overlay')).not.toBeInTheDocument();
  });
});
