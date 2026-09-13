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
      acceptDownloads: true,
      viewport: { width: 1440, height: 1000 },
    });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto(process.argv[2] || "http://127.0.0.1:8769/");
    const data = await page
      .locator("#review-data")
      .evaluate((el) => JSON.parse(el.textContent));
    await page.locator("#missed").uncheck();
    const image =
      data.boards[Number(await page.locator("#board").inputValue())].image;
    await page
      .locator("#note")
      .fill("AUTOMATED PIPELINE CHECK: not a human review or correction.");
    await page.locator("#save-note").click();
    await page.locator("#mode").selectOption("prediction");
    await page
      .locator("#note")
      .fill("AUTOMATED PREDICTION NOTE: not an expert finding.");
    await page.locator("#save-note").click();
    async function exported() {
      const pending = page.waitForEvent("download");
      await page.locator("#export").click();
      return JSON.parse(fs.readFileSync(await (await pending).path(), "utf8"));
    }
    const original = await exported();
    expect(original.notes).toHaveLength(2);
    const file = (doc) => ({
      name: "notes.json",
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(doc)),
    });
    await page.reload();
    await page.locator("#import-notes").setInputFiles(file(original));
    await expect(page.locator("#notes-status")).toContainText(
      "Imported 2 new notes",
    );
    expect((await exported()).notes).toEqual(original.notes);
    await page.locator("#import-notes").setInputFiles(file(original));
    await expect(page.locator("#notes-status")).toContainText(
      "Imported 0 new notes",
    );
    const bad = structuredClone(original);
    bad.checkpoint_sha256 = "0".repeat(64);
    await page.locator("#import-notes").setInputFiles(file(bad));
    await expect(page.locator("#import-error")).toContainText("another run");
    expect((await exported()).notes).toEqual(original.notes);
    const b = data.boards.find((b) => b.image === image);
    const conflict = structuredClone(original);
    const extra = {
      ...structuredClone(
        original.notes.find((n) => n.subject_kind === "annotation"),
      ),
      annotation_index: 1,
      annotation: b.annotations[1],
    };
    conflict.notes = [
      extra,
      { ...original.notes[0], note: "Conflicting synthetic note" },
    ];
    await page.locator("#import-notes").setInputFiles(file(conflict));
    await expect(page.locator("#import-error")).toContainText(
      "Conflicting note",
    );
    expect((await exported()).notes).toEqual(original.notes);
    const forged = structuredClone(original);
    forged.notes.find(
      (n) => n.subject_kind === "prediction",
    ).overlap_context.best_any_class.iou = 0.123456;
    await page.locator("#import-notes").setInputFiles(file(forged));
    await expect(page.locator("#import-error")).toContainText(
      "overlap context",
    );
    expect((await exported()).notes).toEqual(original.notes);
    await page
      .locator("#note")
      .fill("Unsaved draft must survive failed import.");
    await page.locator("#import-notes").setInputFiles(file(original));
    await expect(page.locator("#import-error")).toContainText(
      "Save the current draft",
    );
    await expect(page.locator("#note")).toHaveValue(
      "Unsaved draft must survive failed import.",
    );
    const axe = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(axe.violations).toEqual([]);
    await page.setViewportSize({ width: 390, height: 844 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    expect(errors).toEqual([]);
    fs.mkdirSync(".runtime", { recursive: true });
    fs.writeFileSync(
      ".runtime/review-import-smoke-notes.json",
      JSON.stringify(original, null, 2),
    );
    fs.writeFileSync(
      ".runtime/review-import-browser-check.json",
      JSON.stringify(
        {
          restoredNotes: 2,
          idempotentImport: true,
          atomicConflictRejection: true,
          sourceAndContextVerification: true,
          unsavedDraftPreserved: true,
          axeViolations: 0,
          mobileOverflow: false,
          pageErrors: errors,
          scope: "Automated synthetic notes only; no expert adjudication.",
        },
        null,
        2,
      ),
    );
    console.log("Review import browser checks passed.");
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
