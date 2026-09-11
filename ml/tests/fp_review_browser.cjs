// Manual browser acceptance for the generated corrected tile-model review.
const {
  chromium,
  expect,
} = require("../../frontend/node_modules/@playwright/test");
const AxeBuilder =
  require("../../frontend/node_modules/@axe-core/playwright").default;
const fs = require("node:fs");
(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
      acceptDownloads: true,
    });
    const page = await context.newPage(),
      errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto(process.argv[2] || "http://127.0.0.1:8768/");
    const data = await page
      .locator("#review-data")
      .evaluate((el) => JSON.parse(el.textContent));
    expect(data.boards).toHaveLength(32);
    const collision = data.boards.flatMap((b, i) =>
      b.profiles["0.25"].prediction_matches
        .filter(
          (m) =>
            m.outcome !== "matched" &&
            m.prediction_index < b.annotations.length &&
            b.predictions[m.prediction_index].score >= 0.5,
        )
        .map((m) => ({ board: i, index: m.prediction_index })),
    )[0];
    expect(collision).toBeTruthy();
    await page.locator("#board").selectOption(String(collision.board));
    await page.locator("#missed").uncheck();
    await page
      .locator(`#targets button[data-index="${collision.index}"]`)
      .click();
    await page
      .locator("#note")
      .fill("Annotation note: automated acceptance only.");
    await page.locator("#mode").selectOption("prediction");
    await page
      .locator(`#targets button[data-index="${collision.index}"]`)
      .click();
    await page
      .locator("#note")
      .fill("Prediction note: automated acceptance only.");
    const box = await page
      .locator("#prediction-layer .selected")
      .evaluate((r) =>
        ["x", "y", "width", "height"].map((k) => Number(r.getAttribute(k))),
      );
    expect(box).toEqual(
      data.boards[collision.board].predictions[collision.index].bbox,
    );
    await page.locator("#threshold").selectOption("0.5");
    const pending = page.waitForEvent("download");
    await page.locator("#export").click();
    const download = await pending;
    const result = JSON.parse(fs.readFileSync(await download.path(), "utf8"));
    expect(result.schema_version).toBe("1.1");
    expect(result.notes).toHaveLength(2);
    expect(result.notes.map((n) => n.subject_kind).sort()).toEqual([
      "annotation",
      "prediction",
    ]);
    const note = result.notes.find((n) => n.subject_kind === "prediction");
    expect(note.prediction_index).toBe(collision.index);
    expect(note.score_threshold).toBe(0.25);
    expect(note.overlap_context).toEqual(
      data.boards[collision.board].profiles["0.25"].prediction_matches.find(
        (m) => m.prediction_index === collision.index,
      ),
    );
    expect(
      result.notes.find((n) => n.subject_kind === "annotation")
        .annotation_index,
    ).toBe(collision.index);
    expect(result.matching_code_sha256).toBe(data.matching_code_sha256);
    await page.locator("#top-fp").click();
    let boardIndex = Number(await page.locator("#board").inputValue());
    let predIndex = Number(
      await page
        .locator('#targets button[aria-pressed="true"]')
        .getAttribute("data-index"),
    );
    const allFP = data.boards.flatMap((b) =>
      b.profiles["0.5"].prediction_matches
        .filter((m) => m.outcome !== "matched")
        .map((m) => b.predictions[m.prediction_index].score),
    );
    expect(data.boards[boardIndex].predictions[predIndex].score).toBe(
      Math.max(...allFP),
    );
    await page.locator("#context").selectOption("class_confusion");
    await page.locator("#top-fp").click();
    boardIndex = Number(await page.locator("#board").inputValue());
    predIndex = Number(
      await page
        .locator('#targets button[aria-pressed="true"]')
        .getAttribute("data-index"),
    );
    await page
      .locator("#class")
      .selectOption(
        String(data.boards[boardIndex].predictions[predIndex].category_id),
      );
    expect(await page.locator("#annotation-layer rect").count()).toBe(
      data.boards[boardIndex].annotations.length,
    );
    await expect(page.locator("#overlap-detail")).toContainText(
      "Any class: annotation",
    );
    await page.locator("#labels").uncheck();
    expect(await page.locator("#annotation-layer rect").count()).toBe(0);
    await page.locator("#labels").check();
    await page.locator("#class").selectOption("all");
    await page.locator("#context").selectOption("no_overlap");
    const empty = data.boards.findIndex(
      (b) =>
        !b.profiles["0.5"].prediction_matches.some(
          (m) => m.outcome === "no_overlap",
        ),
    );
    if (empty >= 0) {
      await page.locator("#board").selectOption(String(empty));
      await expect(page.locator("#note")).toBeDisabled();
      await expect(page.locator("#focus")).toBeDisabled();
    }
    await page.locator("#context").selectOption("all");
    await page.locator("#top-fp").click();
    const original = await page.locator("#board").inputValue();
    await page.locator("#next").click();
    await page.locator("#previous").click();
    await expect(page.locator("#board")).toHaveValue(original);
    await page.locator("#focus").click();
    const before = await page.locator("#canvas").getAttribute("viewBox");
    await page.locator("#zoom-in").click();
    expect(await page.locator("#canvas").getAttribute("viewBox")).not.toBe(
      before,
    );
    const near = data.boards.flatMap((b, i) =>
      b.profiles["0.5"].prediction_matches
        .filter(
          (m) =>
            m.outcome === "partial_overlap" &&
            m.best_any_class.iou > 0.4995 &&
            m.best_any_class.iou < 0.5,
        )
        .map((m) => ({ board: i, match: m })),
    )[0];
    expect(near).toBeTruthy();
    await page.locator("#board").selectOption(String(near.board));
    await page
      .locator(`#targets button[data-index="${near.match.prediction_index}"]`)
      .click();
    await expect(page.locator("#overlap-detail")).toContainText(
      near.match.best_any_class.iou.toFixed(6),
    );
    const axe = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(axe.violations).toEqual([]);
    fs.mkdirSync(".runtime", { recursive: true });
    await page.screenshot({
      path: ".runtime/fp-review-desktop.jpg",
      type: "jpeg",
      quality: 60,
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 844 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: ".runtime/fp-review-mobile.jpg",
      type: "jpeg",
      quality: 60,
      fullPage: true,
    });
    expect(errors).toEqual([]);
    fs.writeFileSync(
      ".runtime/fp-review-browser-check.json",
      JSON.stringify(
        {
          coordinateMatch: true,
          annotationPredictionNoteIsolation: true,
          originalThresholdAndContextPreserved: true,
          highestScoreNavigation: true,
          allClassAnnotationContext: true,
          filtersAndEmptyState: true,
          zoomAndNavigation: true,
          axeViolations: 0,
          mobileHorizontalOverflow: false,
          pageErrors: errors,
        },
        null,
        2,
      ),
    );
    console.log("False-positive review browser checks passed.");
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
