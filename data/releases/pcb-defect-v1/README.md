# PCB-Defect research release 1.0.0

Frozen on 2026-09-08. This release is ready for a six-class research baseline under the
recorded integrity gates. It is not a production dataset or evidence of model accuracy.

| Split | Images | Annotations | Conservative groups |
| --- | ---: | ---: | ---: |
| Train | 165 | 1,230 | 9 |
| Validation | 32 | 232 | 2 |
| Test | 33 | 242 | 2 |
| Total | 230 | 1,704 | 13 |

All six classes occur in each split. Full counts and zero remaining validator findings are
recorded in [validation.json](validation.json).

## Frozen artifacts

- [Manifest](../../manifests/pcb-defect-v1.0.json): exact source image hashes, six labels,
  pixel xyxy boxes, group IDs and splits.
- [Release](release.json): manifest/license/review hashes, original COCO image IDs and names,
  family-to-group mapping, group-level counts and immutable assignments.
- [Grouping review](group-review.json): all 30 candidate pairs, decisions and reasons.
- Native JPEGs and license evidence: ignored data/processed/pcb-defect-v1.

Manifest SHA-256:
`31bc9c3df24a42dae1b577ea7082a4c0906fd26a5fb4ecf095af2853d43b26b4`.

Model-local label IDs 0–5 are missing_pad, mouse_bite, open_circuit, short_circuit, spur,
spurious_copper. They are distinct from the nine-class roadmap's canonical IDs.
Source category 0 is unused and excluded; source IDs 1–6 become model IDs 0–5.
COCO [x,y,w,h] boxes become [x,y,x+w,y+h]; image bytes are unchanged.

## Grouping review and limits

The original image names provide 22 first-prefix families (50–68, 80–82). These prefixes
are provenance clues, not verified physical board identities. Every source family stays intact.

First/middle/last images were visually reviewed for every family. All 26,335 image pairs
were considered; cross-family pairs were screened under eight rotations/reflections using
aHash and DCT pHash. Thirty candidates were visually inspected. Five were marked different
layouts; the remaining 25 were conservatively grouped. The review uses 300×250 thumbnails,
aHash64 distance <=8 and AC-only pHash63 distance <=12. pHash uses the quality-80 review JPEG.
These are candidate-generation settings, not learned accuracy thresholds.

Conservative transitive groups combine:
- 57 and 82;
- 59, 60, 61, 62, 63, 68, 80 and 81;
- 64 and 65.

All other families remain separate. Merges include sufficiently related or uncertain layouts,
not just identical images. This deliberately sacrifices some group granularity to limit leakage.
No candidate can cross splits without a recorded different-layout decision.
Exact source byte/pixel checks found no duplicates; the standard validator's additional
cross-split thumbnail check has no findings.

This process does not establish that all remaining groups are independent physical designs.
Global thumbnail hashes can miss crops, perspective changes and local template reuse.
No independent expert annotation-completeness audit, clean-board negative set or external
phone/camera holdout is included. Only two conservative groups in each holdout means
uncertainty must be reported by group; avoid broad generalization claims.

## Split algorithm

Splits were chosen before training. Target fractions are 70/15/15; whole groups take priority.
With 13 groups, two groups go to each holdout. Test groups are selected first, validation
groups second. For each eligible group combination, minimize the sum of squared deviations
from 15% of total images and of each class's annotation count. Preserve all six classes
in the selected and remaining groups. Break equal-score ties by SHA-256 of sorted group IDs.
No model metrics, seed search or post-training reassignment enters this selection.

Train: family roots 50, 53, 54, 55, 56, 58, 59, 66, 67.
Validation: roots 51, 52. Test: roots 57, 64.
Do not reuse the test set to choose transforms, confidence thresholds or model versions.

## Reproduce

Use the pinned PCB-Defect archive described in [data/README.md](../../README.md), then run
from the repository root:

```powershell
.\.venv\Scripts\python.exe scripts/prepare_pcb_defect.py review
.\.venv\Scripts\python.exe scripts/prepare_pcb_defect.py build
.\.venv\Scripts\python.exe -m pcb_inspector.datasets data/manifests/pcb-defect-v1.0.json --root data/processed/pcb-defect-v1 --purpose research --max-image-pixels 40000000 --output .runtime/pcb-defect-v1-validation.json
```

Review regenerates the same candidate pairs and thumbnails under ignored data/interim.
Build checks candidates against the recorded decisions, verifies the source hash and class map,
and refuses to replace any frozen artifact or source image with differing bytes.
A second build reproduced the exact manifest and release bytes.

Offline validation explicitly allows up to 40 MP to preserve all originals, including ten
above 20 MP. The default validator bound and production upload limit remain 20 MP.
The validation report records the selected limit. This release does not resize or tile images;
those transforms belong in a separately versioned training experiment, with all tiles
inheriting their source image's split.

Only research usage is recorded in this release. Attribution and the CC BY 4.0 source
declarations are preserved in the local license evidence. No expert/legal approval is invented.

## Next step

Implement a reproducible training/evaluation baseline with a reviewed framework/weight license,
native-resolution tiling versus resize experiments on training/validation, MLflow evidence,
and per-class/group evaluation. Keep inference demo-only until an evaluated surface model
and its versioned report contract are integrated.
