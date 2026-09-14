# Candidate dataset audit - 2026-09-14

Status: research candidates only; neither source is released for training or production.
Original archives and annotations were preserved. No archive scripts were executed and no
model inference or training was performed. Existing project test holdout is unchanged.

| Measured property | MeiweiPCB | DsPCBSD+ |
| --- | --- | --- |
| Images | 969 defect + 969 normal references | 10,259 defect images |
| Boxes | 1,275 generic defect boxes | 20,276 boxes, nine classes |
| Size | All 220x220 | 10,148 at 226x226; 111 at 108x108 |
| Source splits | 581 train / 194 validation / 194 test defect images | 8,208 train / 2,051 validation; no test split |
| Exact cross-split pixel duplicates | Two groups among paired normal references | None in COCO images |
| Cross-split dHash candidates | 14 defect pairs; 29 normal pairs | 453 pairs |

Sources: [pinned Meiwei repository](https://github.com/youtang1993/MeiweiPCB/tree/c19045cec8010a7576251fb24ef0c03c1c0ebefb)
and [DsPCBSD+ publisher](https://figshare.com/articles/dataset/DsPCBSD_/24970329).
DsPCBSD+ archive matches publisher size (128,541,608 bytes) and MD5
508334b65bdaea7336f4c1b5d5a80a81. Publisher metadata declares CC BY 4.0;
Meiwei repository includes Apache-2.0, with dataset provenance/applicability still to review.

## Findings and decisions

Meiwei has 969 one-to-one Cur/Ref filename pairs. Normal references inherit their paired
source split only for this audit. Two exact duplicate normal groups cross those splits;
all related pairs must be grouped before a candidate split can be frozen. The two broad
filename family hints span every split and are not verified physical-board identities.
Six sampled pairs were visually consistent with aligned defect/reference crops. This is
not expert confirmation that every reference is normal or that annotations are complete.
One exact defect duplicate group and three exact normal duplicate groups exist in total.

DsPCBSD+ COCO and YOLO image copies match byte-for-byte and must not be double-counted.
All COCO images have annotations; this is not a clean-negative collection. There are 277
boxes outside image bounds beyond the audit's 1e-6-pixel tolerance. The maximum observed
overshoot is about 0.0113 pixels. A separate proposal list clips only overshoots up to
0.02 pixels, covering those 277 plus 94 negligible floating-point discrepancies.
All 371 proposals preserve positive box area; none have been applied to source data.
Rounding is a plausible explanation, not a verified account of the source conversion.

Near-duplicate counts use 64-bit dHash at distance <=2, original orientation only.
They are review candidates, not proof of leakage or a guarantee of independence. Six
DsPCBSD+ candidate pairs were inspected: some were visibly different repetitive patterns,
while one looked closely related. Do not automatically merge or delete heuristic matches.
Reports retain the first 100 candidates per collection; full counts are recorded.

## Next training preparation

1. Review source provenance, normal-label completeness, pair alignment and source grouping.
   Build a reviewable group manifest keeping exact duplicates, paired references and
   verified related captures together. Do not invent physical-board identifiers.
2. Review the bounded box proposals and save any accepted corrections as a versioned
   derived annotation release with the untouched source hashes.
3. Keep DsPCBSD+ as a separate nine-class research track initially. SH/SP/SC/OP/MB are
   candidate matches for short_circuit/spur/spurious_copper/open_circuit/mouse_bite, but
   mapping requires review. HB/CS/CFO/BMFO have no approved mapping in the current six-class
   contract. Hole breakout is not missing pad. Never silently drop unmapped defect labels.
4. Freeze an independent evaluation partition before training, with documented group
   evidence. Meiwei generic defects cannot supply six-class labels. Author-labeled normal
   patches may support a reviewed negative-data experiment, not clean whole-board claims.
5. Run the planned matched-budget experiment only after a reviewed release is ready.
   Production additionally requires representative camera/board qualification data and
   the user's still-undecided acceptable defective-board escape rate.

## Reproduction and evidence

Run from the repository root, choosing fresh output directories:

```powershell
.venv\Scripts\python.exe -m ml.candidate_audit meiwei --input data/raw/meiwei-discovery-c19045ce --output ml/runs/meiwei-audit-new
.venv\Scripts\python.exe -m ml.candidate_audit dsp --input data/raw/dspcbsd-plus-v1/DsPCBSD+.zip --output ml/runs/dspcbsd-audit-new
.venv-ml\Scripts\python.exe -m pytest tests/test_ml_views.py ml/tests -q
```

[Meiwei evidence](../ml/evidence/meiwei-source-audit-001.json) and
[DsPCBSD+ evidence](../ml/evidence/dspcbsd-source-audit-001.json) bind archive hashes,
audit code SHA256 and the full local inventory SHA256. Inventories and archives remain
ignored local artifacts; source URLs and acquisition metadata support reacquisition.
The audit reads source test annotations/images for integrity checks only, never model
predictions. Tests: 176 passed, including 14 audit cases covering unsafe archive paths,
size limits, malformed references, exact versus heuristic leakage and bounded correction.
