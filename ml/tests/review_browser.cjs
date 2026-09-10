// Manual acceptance check for the frozen 32-board coco-resize640-5epochs review.
// Run from repository root; uses the frontend's existing Playwright/axe dependencies.
const {
  chromium,
  expect,
} = require("../../frontend/node_modules/@playwright/test");
const AxeBuilder =
  require("../../frontend/node_modules/@axe-core/playwright").default;
const fs = require("node:fs");
(async () => {
  fs.mkdirSync(".runtime", { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    acceptDownloads: true,
  });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(process.argv[2] || "http://127.0.0.1:8766/");
  await expect(
    page.getByRole("heading", { name: "PCB validation review" }),
  ).toBeVisible();
  await expect(page.locator("#board option")).toHaveCount(32);
  await expect(page.locator("#image-error")).toBeHidden();
  await page.waitForFunction(
    () => document.querySelector("#source").href.baseVal.length > 0,
  );
  await page.screenshot({ path: ".runtime/review-full.png", fullPage: true });
  await page.locator("#class").selectOption("2");
  const first = page.locator("#targets button").first();
  await first.click();
  await expect(page.locator("#canvas .selected")).toHaveCount(1);
  const box = await page
    .locator("#canvas .selected")
    .evaluate((r) =>
      ["x", "y", "width", "height"].map((a) => Number(r.getAttribute(a))),
    );
  const expected = await page.locator("#review-data").evaluate((el) => {
    const d = JSON.parse(el.textContent);
    return d.boards[0].annotations.find((a) => a.category_id === 2).bbox;
  });
  expect(box).toEqual(expected);
  const view = await page.locator("#canvas").getAttribute("viewBox");
  expect(Number(view.split(" ")[2])).toBeLessThan(1000);
  await page.screenshot({
    path: ".runtime/review-mouse-014.png",
    fullPage: true,
  });
  await page.locator("#labels").uncheck();
  expect(await page.locator("#annotation-layer rect").count()).toBe(0);
  await page.locator("#predictions").uncheck();
  expect(await page.locator("#prediction-layer rect").count()).toBe(0);
  await page.screenshot({
    path: ".runtime/review-mouse-014-clean.png",
    fullPage: true,
  });
  await page.locator("#labels").check();
  await page.locator("#predictions").check();
  await page
    .locator("#note")
    .fill("Automated UI verification note; not a dataset assessment.");
  await page.locator("#assessment").selectOption("unclear");
  await page.locator("#threshold").selectOption("0.5");
  await expect(page.locator("#notes-status")).toContainText("1 review notes");
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export notes" }).click();
  const download = await downloadPromise;
  const notes = JSON.parse(fs.readFileSync(await download.path(), "utf8"));
  expect(notes.notes).toHaveLength(1);
  expect(notes.notes[0].score_threshold).toBe(0.25);
  expect(notes.notes[0].note).toContain("Automated UI verification");
  await page.getByRole("button", { name: "Next board", exact: true }).click();
  await expect(page.locator("#board")).toHaveValue("1");
  await page
    .getByRole("button", { name: "Previous board", exact: true })
    .click();
  await expect(page.locator("#board")).toHaveValue("0");
  await page.getByRole("button", { name: "Fit board", exact: true }).click();
  const fit = await page.locator("#canvas").getAttribute("viewBox");
  await page.getByRole("button", { name: "Zoom in", exact: true }).click();
  expect(await page.locator("#canvas").getAttribute("viewBox")).not.toBe(fit);
  const axe = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(axe.violations).toEqual([]);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: ".runtime/review-mobile.png", fullPage: true });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
  fs.writeFileSync(
    ".runtime/review-browser-check.json",
    JSON.stringify(
      {
        boards: 32,
        sourceCoordinateMatch: true,
        zoom: true,
        layerToggles: true,
        navigation: true,
        noteExport: true,
        originalNoteThresholdPreserved: true,
        horizontalOverflow: false,
        axeViolations: axe.violations.length,
        pageErrors: errors,
      },
      null,
      2,
    ),
  );
  console.log(
    "Review browser checks passed: coordinates, zoom, filters, layers, navigation, note export, accessibility, mobile layout",
  );
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
