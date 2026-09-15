# Visual candidate review

Open either generated index.html directly in a browser; the packages work offline:

- [Meiwei review](runs/meiwei-visual-review-002/index.html): 1,015 cases, 1,938 verified images.
- [DsPCBSD+ review](runs/dspcbsd-visual-review-002/index.html): 835 cases, 771 selected verified images.

Keep index.html, candidate_viewer.js and the images folder together. The package builder
verifies the committed packet summary, inventory and audit hashes, whole source archive
hashes and every selected image's bytes, pixels and dimensions before writing a package.
Only images used by cases and up to six examples per source class are copied; source files
remain untouched. These are dataset inspection pages, not model predictions or approvals.

## Reviewer flow

1. Enter the actual reviewer identifier. Filter by case type, saved status or filename.
2. Inspect paired images or box corrections. Fit displays the whole image; 2x/4x support
   closer inspection with scrolling. Toggle overlays to inspect the underlying pixels.
   Solid red marks source boxes; dashed yellow marks the proposed box. Tiny differences
   may overlap, so inspect the numerical coordinates in Case reference and coordinates.
3. Answer every field and provide a rationale with reference evidence. Use needs reference
   when the available evidence is insufficient. Class galleries are examples, not an
   exhaustive completeness review; source provenance and independence need outside evidence.
4. Save the decision in the page. The reviewer identifier locks once decisions are saved,
   preventing accidental reassignment of another reviewer's observations.
5. Export saved decisions before closing. There is no server-side or automatic draft storage.
   Unsaved edits prompt before navigation and prevent export. Closing prompts when work is
   present. Restore an exported file to continue; mismatched packets, malformed decisions,
   repeated cases and conflicts with current saved decisions are rejected before mutation.
6. Import the export with [the versioned decision command](CANDIDATE_DECISIONS.md), then
   use [candidate derivation](CANDIDATE_DERIVATION.md) to prepare an unapproved candidate.

Exports use the actual export time with UTC timezone as the batch reviewed_at. They do not
retain per-case observation timestamps; preserve earlier exports and ledger revisions for
history. Browser restore is a convenience check; the Python importer remains authoritative
and additionally rejects duplicate JSON object keys. No fields approve training or production.
If a required image fails to load, saving that visual case is disabled.

## Rebuild

From the repository root, use a fresh output directory:

```powershell
.venv\Scripts\python.exe -m ml.candidate_viewer --packet ml/runs/dspcbsd-candidate-review-001/candidate-review.json --summary ml/evidence/dspcbsd-candidate-review-001.json --inventory ml/runs/dspcbsd-audit-004/inventory.json --audit ml/evidence/dspcbsd-source-audit-001.json --raw data/raw/dspcbsd-plus-v1/DsPCBSD+.zip --output ml/runs/dspcbsd-visual-review-new
```

For Meiwei, use its matching packet/summary/inventory/audit and the archive directory
`data/raw/meiwei-discovery-c19045ce` as --raw. Existing output directories are rejected.
Generated packages remain ignored local data; code and hash-bound summaries are committed.

## Verification

225 ML tests passed. Both complete packages passed browser checks for image loading,
zoom/overlays, blank-answer rejection, export/restore, packet mismatch and conflict rejection,
reviewer locking and missing-image protection. Mobile checks found no horizontal overflow
and no axe accessibility violations; no page errors occurred. Desktop and mobile screenshots
were inspected and a cropped Fit view was corrected. Browser-exported synthetic observations
were accepted by the Python validator and in-memory ledger builder; no synthetic decisions
were written into actual review ledgers. See [evidence](evidence/candidate-visual-review-001.json).

The browser plugin connection failed twice at startup; local Playwright acceptance used the
project's existing browser-test dependencies. Re-run with `node ml/tests/candidate_viewer_browser.cjs`
after generating the version-002 packages. Test downloads/screenshots remain in .runtime.

Next required input is actual expert/source review. Completing the interface does not supply
verified clean whole boards, independent camera data or the still-undecided production
escape-rate target, and no new training run was started.
