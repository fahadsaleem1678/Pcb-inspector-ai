import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import path from 'node:path';

test('upload, inspect, download, reopen and keyboard access', async ({ page }, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to inspection workspace' })).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('heading', { name: 'Your board, in focus.' })).toBeVisible();
  await expect(page.getByText('Demo mode', { exact: true })).toBeVisible();
  const initialAudit = await new AxeBuilder({ page }).analyze();
  expect(initialAudit.violations).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath('empty-workspace.png'), fullPage: true });
  await page
    .getByLabel('Choose PCB image')
    .setInputFiles(path.resolve('../.runtime/e2e-fixtures/board.png'));
  await expect(page.getByRole('img', { name: 'PCB image submitted for inspection' })).toBeVisible();
  await page.getByRole('button', { name: 'Run demo inspection' }).click();
  await expect(page.getByRole('heading', { name: 'Board not evaluated' })).toBeVisible();
  await expect(page.getByText('demo-no-model-0.1.0', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Zoom in' }).click();
  await expect(page.getByLabel('Zoom level')).toHaveText('125%');
  await page.getByRole('button', { name: 'Fit image' }).click();
  await expect(page.getByLabel('Zoom level')).toHaveText('100%');
  const url = page.url();
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download JSON report' }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/\.json$/);
  const stream = await download.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream!) chunks.push(Buffer.from(chunk));
  const report = JSON.parse(Buffer.concat(chunks).toString());
  expect(report.is_demo).toBe(true);
  expect(report.overall_result).toBe('NOT_EVALUATED');
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Board not evaluated' })).toBeVisible();
  await page.getByRole('button', { name: 'New inspection' }).click();
  await expect(page.getByRole('heading', { name: 'Your board, in focus.' })).toBeVisible();
  const id = new URL(url).searchParams.get('inspection')!;
  await page.getByRole('button', { name: `Open inspection ${id.slice(0, 8)}` }).click();
  await expect(page.getByRole('heading', { name: 'Board not evaluated' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  const reportAudit = await new AxeBuilder({ page }).analyze();
  expect(reportAudit.violations).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath('completed-workspace.png'), fullPage: true });
  expect(errors).toEqual([]);
});

test('invalid image and unavailable service produce actionable errors', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Choose PCB image').setInputFiles({
    name: 'corrupt.png',
    mimeType: 'image/png',
    buffer: Buffer.from('not a real image'),
  });
  await page.getByRole('button', { name: 'Run demo inspection' }).click();
  await expect(
    page.getByRole('alert').filter({ hasText: 'Image cannot be safely decoded' }),
  ).toBeVisible();
  await page.route('**/api/v1/inspections?*', (route) => route.abort());
  await page.getByRole('button', { name: 'Refresh history' }).click();
  await expect(
    page.getByRole('alert').filter({ hasText: 'Cannot reach the inspection service' }),
  ).toBeVisible();
});

test('missing inspection stops polling and exposes retry', async ({ page }) => {
  let requests = 0;
  await page.route('**/api/v1/inspections/00000000-0000-0000-0000-000000000001', (route) => {
    requests++;
    return route.fulfill({ status: 404, json: { detail: 'Inspection not found' } });
  });
  await page.goto('/?inspection=00000000-0000-0000-0000-000000000001');
  await expect(page.getByRole('alert').filter({ hasText: 'Inspection not found' })).toBeVisible();
  const baseline = requests;
  await page.getByRole('button', { name: 'Retry connection' }).click();
  await expect.poll(() => requests).toBeGreaterThan(baseline);
});

test('test-only detection overlay stays aligned through zoom', async ({ page }) => {
  const id = '11111111-1111-1111-1111-111111111111';
  await page.route(`**/api/v1/inspections/${id}`, (route) =>
    route.fulfill({
      json: {
        id,
        status: 'COMPLETED',
        created_at: '2026-09-07T10:00:00Z',
        completed_at: '2026-09-07T10:00:01Z',
        width: 640,
        height: 400,
        attempts: 1,
        model_version: 'test-fixture-only',
        error_code: null,
        overall_result: 'REVIEW_REQUIRED',
      },
    }),
  );
  await page.route(`**/api/v1/inspections/${id}/image`, (route) =>
    route.fulfill({
      path: path.resolve('../.runtime/e2e-fixtures/board.png'),
      contentType: 'image/png',
    }),
  );
  await page.route(`**/api/v1/inspections/${id}/results`, (route) =>
    route.fulfill({
      json: {
        schema_version: '1.0',
        inspection_id: id,
        model_version: 'test-fixture-only',
        is_demo: false,
        overall_result: 'REVIEW_REQUIRED',
        inference_time_ms: 10,
        image_width: 640,
        image_height: 400,
        ignored_detection_count: 0,
        decision_policy_version: 'test-fixture',
        limitations: ['Synthetic UI test response only.'],
        detections: [
          {
            defect_type: 'solder_bridge',
            confidence: 0.94,
            severity: 'critical',
            confidence_band: 'high',
            bbox: { x1: 200, y1: 150, x2: 260, y2: 180 },
          },
        ],
      },
    }),
  );
  await page.goto(`/?inspection=${id}`);
  await expect(page.getByRole('heading', { name: 'Review required' })).toBeVisible();
  const region = page.getByRole('button', { name: 'Region 1: solder bridge' });
  await expect(region).toBeVisible();
  const image = page.getByRole('img', { name: 'PCB image submitted for inspection' });
  for (const zoom of [100, 125]) {
    if (zoom === 125) await page.getByRole('button', { name: 'Zoom in' }).click();
    const imageBounds = await image.boundingBox();
    const boxBounds = await region.boundingBox();
    expect(imageBounds).not.toBeNull();
    expect(boxBounds).not.toBeNull();
    expect((boxBounds!.x - imageBounds!.x) / imageBounds!.width).toBeCloseTo(200 / 640, 2);
    expect((boxBounds!.y - imageBounds!.y) / imageBounds!.height).toBeCloseTo(150 / 400, 2);
    // The group's visual bounds include a 2px non-scaling outline.
    expect((boxBounds!.width - 2) / imageBounds!.width).toBeCloseTo(60 / 640, 3);
  }
  await region.focus();
  await page.keyboard.press('Enter');
  await expect(region).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('button', { name: /1 solder bridge/i })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
});
