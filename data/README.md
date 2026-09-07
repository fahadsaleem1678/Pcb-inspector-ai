# Dataset inventory and acquisition gate

No datasets or model weights have been downloaded. Checked 2026-09-07.

| Candidate | Coverage | Usage evidence | Disposition |
| --- | --- | --- | --- |
| [DeepPCB](https://github.com/tangsanli5201/DeepPCB) | 1,500 aligned template/test pairs; open, short, mousebite, spur, copper and pin-hole labels | [MIT repository license](https://github.com/tangsanli5201/DeepPCB/blob/master/LICENSE), but README explicitly restricts the dataset to research | Research candidate only; public/commercial model use unresolved; classes do not cover proposed assembled-board taxonomy |
| Assembled-board AOI data | Missing/misaligned/damaged components, solder bridges, debris, board damage and contamination | Source, rights and coverage not established | Identify suitable sources or collect owned/authorized images before training |

DeepPCB also describes synthetic defect augmentation. Its paired/template-oriented images and
evaluation protocol need separate consideration from unrestricted user photos. Preserve original
labels; do not describe bare-board shorts as validated solder-bridge detection. These observations
come from the project's [dataset description](https://github.com/tangsanli5201/DeepPCB#dataset-description).

Every acquired dataset manifest must include source URL and revision, checksum, license evidence,
permitted uses, acquisition date, label map, image/board grouping, provenance of augmentations,
class counts, split assignment and annotation validation results. Keep physical board/template
groups and their derivatives in one split to prevent leakage. Keep a held-out test set unchanged.

Store acquisitions under `raw/`, intermediate data under `interim/`, normalized data under
`processed/`, and versioned manifests/labels/splits under source control or DVC. Large data and
weights are gitignored. Do not choose an application software license on behalf of dataset owners.
