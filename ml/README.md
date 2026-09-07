# Dataset preparation and model gate

No real detector or dataset has been selected. Keep the original assembled-board taxonomy
provisional until authorized data is found. The current detector remains explicitly demo-only.

The first preparation tool is `python -m pcb_inspector.datasets`. It validates a manifest and
local images without downloading data, changing annotations or training a model.

```powershell
.\.venv\Scripts\python.exe -m pcb_inspector.datasets data/manifests/dataset-v1.json --root data/raw/dataset-v1 --purpose research --output .runtime/dataset-validation.json
```

Exit codes: 0 means the recorded integrity/usage gates passed; 1 means errors or review findings
need attention; 2 means the manifest could not be parsed/read. A passing report does not
independently prove license rights, dataset quality, adequate sample count or model accuracy.
The license fields record a review performed by the dataset owner/reviewer.

Start with `data/manifest.template.json` and the JSON schema in `data/manifest.schema.json`.
The template intentionally fails validation until source/version, evidence, reviewer/date,
permitted purposes and sample records are supplied. Do not fill license approval fields without
an actual review. Evidence must be a nonempty file within the dataset root.

Each sample has a relative image path, byte SHA-256, decoded width/height, physical
board/template `group_id`, split (`train`, `validation`, `test`) and an annotation list.
Annotations use zero-based `class_id` into the class map and pixel boxes `{x1,y1,x2,y2}`.
An empty annotation list is allowed for a negative image. Normalize EXIF orientation and
annotations together before validation; the validator does not silently transform coordinates.

Checks include path containment, image decoding and limits, byte checksums, duplicate paths,
identical byte/pixel content, box bounds, class coverage and physical-group split leakage.
A coarse 8×8 grayscale hash flags likely cross-split visual duplicates for human review.
It can produce false positives and miss transformed duplicates; it does not replace a
proper near-duplicate/embedding audit. Missing classes in any split also require review.
Perceptual comparison is quadratic across splits and intended for initial dataset exploration.

`grouped_split(group_ids, seed="pcb-v1")` in `pcb_inspector.datasets` provides deterministic,
order-independent group assignment (~70/15/15, with at least one group per split).
For example, import it in a preparation script, then persist each returned split in the
manifest. It requires at least three independent groups. Assignment is not class-stratified:
check the resulting coverage. Adding groups can change assignments, so freeze the manifest
and preserve the held-out test set; do not rerun splitting against a growing production dataset.

Before M3 training is complete, add an authorized dataset, DVC versioning, grouped/duplicate
audits, a calibrated quality/compatibility gate, a detector training adapter, MLflow runs,
per-class held-out evaluation, and an artifact/label-map promotion contract.
