# Dataset inventory and acquisition audit

V1 now targets **surface defects**. Read the [Dataset V1 specification](../docs/dataset-v1-spec.md)
for source decisions, verified class mappings, splits, quality gates and training exclusions.

Two original Mendeley archives were downloaded and checksum-verified on 2026-09-07.
PCB-Defect contains 230 images / 1,704 boxes. MIXED V4 contains 1,741 images / 3,936 rows.
PCB-IND's archive remains unavailable here (Zenodo HTTP 403); its paper and GitHub class maps
conflict. PCB-AoI belongs to V2. DeepPCB and PKU remain separate excluded reference sources.

## Reproduce the audit

Install the project's Python dependencies. Download each original file using the preview link
in [source-lock.json](source-lock.json); the downloaded-file endpoints returned 403 during this
audit while the supplied preview endpoints served the complete ZIP files.

Save PCB-Defect as data/raw/source-audit/defect.zip and MIXED as
data/raw/source-audit/mixed.zip. Do not unzip or execute upstream scripts.

```powershell
.\.venv\Scripts\python.exe scripts/audit_dataset_archives.py
```

The script requires the exact pinned archive hashes, reads images and annotations inside the
archives, checks dimensions/box bounds/references, records exact duplicates and cross-split
filename-family candidates, and creates deterministic annotated contact sheets.
Outputs go to ignored data/interim/source-audit. It is an acquisition audit, not a training gate:
successful execution means a report was generated; inspect issues and ready_for_training
(which deliberately remains false). Exceptions indicate an unreadable or unexpected archive.
It does not download files, assign physical board IDs, certify labels or train a model.

Compact measured reports are committed in audits/2026-09-08. Full per-image reports, source
snapshots, archives and contact sheets remain locally available in ignored directories.
The reports record review limitations, not just successful integrity checks.

## Storage and rights

Keep immutable acquisitions under raw/, intermediates under interim/, normalized data under
processed/. Commit small provenance records, mappings and frozen split manifests; use DVC
for large datasets and weights. Retain author attribution, original DOI/version, license URL,
source checksums and modification notices when creating derived releases.
CC BY 4.0 attribution requirements are described by [Creative Commons](https://creativecommons.org/licenses/by/4.0/).

The strict manifest validator remains available; see [ml/README.md](../ml/README.md).
The [PCB-Defect research release](releases/pcb-defect-v1/README.md) now has a frozen
six-class manifest: 165 train / 32 validation / 33 test images in 13 conservative groups.
All integrity gates pass with the explicit 40 MP offline decode limit. Annotation completeness,
clean-board negatives and external-domain evaluation remain production gates. The generic
template intentionally lacks usage review and samples.
