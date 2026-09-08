# Dataset V1 specification

Decision date: 2026-09-08. Acquisition began 2026-09-07.
Status: **surface-defect scope accepted; data release not yet training-ready**.

## Product scope

V1 is **PCB Inspector AI: AI-assisted PCB surface defect inspection**. This decision
supersedes the assembled-component targets in the original architecture for V1.
Component placement, solder paste, solder joints and assembly inspection move to V2.
Results describe visible findings, not electrical continuity or manufacturing certification.

The nine requested surface classes are the product roadmap, not nine demonstrated model
capabilities. Freeze the identifiers in [taxonomy-v1.json](../data/taxonomy-v1.json).
The first reproducible baseline will use PCB-Defect's six verified classes. Missing hole,
pin hole and scratch remain unavailable until suitable annotations are acquired and evaluated.
Keep missing pad, missing hole, pin hole and missing copper distinct.

The running application remains demo-only. Its legacy report enum still contains assembly
labels; replace/version that contract, severity policy, generated client types and tests when
integrating the surface model. Do not reuse old component labels for surface detections.

## Source selection and actual evidence

| Source | Role and revision | Decision |
| --- | --- | --- |
| PCB-Defect | Initial six-class baseline; Mendeley vdj74sngvn V1 | Acquired and structurally audited; group review and training manifest next |
| PCB-IND | Intended primary industrial source; paper cites Zenodo 19723114, archive v4 | Pending acquisition and class-map reconciliation; do not train from GitHub IDs |
| MIXED PCB DEFECT | Optional training-only augmentation; Mendeley fj4krvmrr5 V4 | Acquired but excluded from V1.0: missing class-name map and unresolved source/derivative lineage |
| PCB-AoI | Separate V2 solder-paste track | Excluded from surface training and benchmarks |
| DeepPCB | Separate research reference | Excluded from V1 training pending resolution of research-only dataset wording |
| PKU/HRIPCB | Separate synthetic/reference source | Excluded pending original rights and derivative provenance review |

Do not merge all sources and randomly split images. Add sources in versioned experiments,
compare against the same frozen benchmark, and retain source-specific metrics.

### PCB-Defect: measured archive findings

The acquired archive matches Mendeley's SHA-256. It contains 230 JPEGs and 1,704 COCO boxes.
Source IDs 1–6 are missing_pad, mouse_bite, open_circuit, short, spur, spurious_copper.
ID 0 is an unused parent category, not a seventh defect class.
Counts respectively: 276, 356, 276, 254, 296, 246.

All images decoded; dimensions agree with COCO metadata; all boxes are within bounds.
No exact byte or decoded-pixel duplicates were found. This does not prove board independence
or complete/correct annotations. There are **no negative images**.

Measured resolution is 2.567–31.264 MP, mean **8.129 MP**, rather than the landing page's
6.61 MP average quoted in the proposal. Ten images exceed the API's current 20 MP limit.
The largest is 5971×5236. The actual layout is images/ plus annotation/_annotations.coco.json.
COCO extra.name retains original names such as 61-1-4.png: preserve them as grouping clues,
not verified board identities.

Twelve evenly spaced images were visually reviewed with boxes. They show yellow/green
substrates, broad board layouts and small localized annotations. This is an exploratory
sample, not expert validation of every defect. Mean box area is about 0.17% of image area;
blindly reducing entire boards to 640 pixels risks losing small defects.

The original deposit and embedded COCO license both declare CC BY 4.0. Attribution:
Rashid, Ullah, Isfara, Ahmed, Mian and Shalehin, PCB-Defect, V1,
[doi:10.17632/vdj74sngvn.1](https://data.mendeley.com/datasets/vdj74sngvn/1).
The [paper](https://doi.org/10.1016/j.dib.2025.112296) describes chemically induced defects
and flatbed scanning. These are physical defects in a laboratory acquisition domain.

### PCB-IND: conflicting class dictionaries

The [repository](https://github.com/gnmtdt/PCB-IND/tree/3b0db4f9ab63a98f79a72f4feca267d85cfd9a1d)
lists missing_hole, mouse_bite, open_circuit, short, spur, spurious_copper, pin_hole, scratch
at IDs 0–7. However, Table 3 of the
[reference manuscript](https://www.nature.com/articles/s41597-026-07684-4_reference.pdf)
lists the following:

| ID | Manuscript | GitHub data.yaml |
| --- | --- | --- |
| 0 | Mouse Bite | missing_hole |
| 1 | Missing Copper | mouse_bite |
| 2 | Scratch | open_circuit |
| 3 | Spurious Copper | short |
| 4 | Copper Burr | spur |
| 5 | Stain | spurious_copper |
| 6 | Short | pin_hole |
| 7 | Open | scratch |

The paper reports 4,789 images / 5,932 instances in **300×300 AOI candidate crops**,
with a center bias and an official 8:1:1 split. These counts were not independently measured.
It points to [Zenodo 19723114](https://doi.org/10.5281/zenodo.19723114) and a classes.json
inside PCB-IND v4.zip. Zenodo page/API requests returned HTTP 403 in this environment.

Acceptance requires the pinned archive, its classes.json, annotation category IDs and visual
examples to agree. Do not guess whether copper burr equals spur or missing copper equals
missing pad. Preserve stain/missing copper as unmapped source labels until reviewed.
Inspect one annotation format; COCO/VOC/YOLO copies are not three independent datasets.
The dataset is declared CC BY 4.0; the article has separate CC BY-NC-ND terms.
Do not treat publication figure permissions as dataset permissions.

### MIXED: measured archive findings

The V4 archive checksum matches its [original deposit](https://data.mendeley.com/datasets/fj4krvmrr5/4).
It contains 1,741 images, all 640×640, and **3,936 YOLO rows**. Splits contain
1,720 train, 10 valid and 11 test images. Numeric IDs 0–5 occur, but no data.yaml,
classes file or embedded license file is present. The deposit declares CC BY 4.0.

All images decoded and boxes are in bounds; no exact duplicates were found. Four filename
families before the Roboflow .rf. suffix span splits. These are leakage candidates, not proof
that every similarly named image is the same board. Neither source split is a credible
standalone production benchmark at this size. No images have empty annotations.

Visual review shows saturated green PCB crops, rotation and varying appearance. Retain the
authors' declared augmentation lineage; do not interpret a 2026 metadata version as fresh
2026 image capture. Resolve original parent data rights and numeric label names before use.
Do not infer names from filenames or from another YOLO dataset's ordering.

### Deferred sources

The [PCB-AoI authors' description](https://github.com/kubeedge/ianvs/blob/main/docs/proposals/scenarios/industrial-defect-detection/pcb-aoi.md)
describes 173 training and 60 test boards, 1,211 augmented training images, and VOC labels.
The [authors' Kaggle listing](https://www.kaggle.com/datasets/kubeedgeianvs/pcb-aoi)
declares Apache 2.0. Samples were not acquired in this audit. Its solder-paste labels belong
in a separate V2 model and taxonomy.

[DeepPCB](https://github.com/tangsanli5201/DeepPCB) is distinct from PKU/HRIPCB.
Its repository's research-only dataset wording remains unresolved for the public product.
A mirror's CC0 declaration does not establish rights to its upstream content.

## Normalization and release artifacts

1. Preserve original archives, checksums, source versions, license evidence and attribution.
   Large data stay under ignored data/raw, data/interim and data/processed directories.
2. Build a per-source manifest before a composite release. Preserve source image/category IDs,
   original names, acquisition domain, board/template/batch, parent image, augmentation
   history and annotated-class coverage. Unknown provenance remains explicitly unknown.
3. Decode offline at native resolution with bounded resources. Keep the production upload cap
   unchanged. Evaluate overlap tiling versus resizing; preserve crop offsets and transforms,
   clip boxes consistently, and audit truncated targets. Every tile follows its parent's split.
4. Normalize COCO xywh and YOLO normalized boxes to pixel xyxy. Map names explicitly using the
   checked-in taxonomy; preserve original annotations and record every transformation.
5. Exclude unknown source classes from a mixed training release until they can be represented
   or explicitly masked. An unannotated class is **unknown**, not a negative. Standard detector
   losses need complete union labels, separate heads, or a tested partial-label strategy.
6. Version raw data/derived manifests with DVC; pin transforms, code, seed and checksums.
   The existing manifest 1.0 is single-source: extend it before representing mixed licenses,
   source-level annotation coverage and held-out external domains. Do not collapse all rights
   into one artificial license record.

No training manifest or approval fields were fabricated by this audit.

## Splits and leakage prevention

For PCB-Defect V1.0, target **70/15/15 by verified independent group**, approximately
161/35/34 images only if all 230 boards are independent. Those numbers are targets,
not assigned splits. Group same board, layout/template, acquisition session and all derivatives
together; review original-name hints and image similarity before choosing group IDs.

Use exact byte/pixel hashes across all sources, then rotation/flip-aware perceptual similarity,
crop/embedding candidates and human review. Merge related groups before splitting. Retain
candidate pairs and decisions, including false positives. The audit script only checks exact
duplicates and filename hints; the existing coarse hash is not sufficient for release.

Stratify at group level using class presence. Require every supported class in train, validation
and test; report positive images, instances and independent groups per class. If rare classes
cannot survive independent splitting, gather data or narrow the supported subset. Never move
test examples after looking at model performance to improve results.

For PCB-IND, preserve its official split for an explicitly named replication experiment.
Audit group/duplicate separation independently; create a separate grouped evaluation if
needed and do not claim direct comparability to published numbers after changing splits.
Optional MIXED derivatives are training-only and must not overlap any evaluation groups.

Freeze test manifests before training. Tune preprocessing, confidence and rejection thresholds
on training/validation only. Keep a separate, licensed, naturally captured phone/camera
holdout spanning lighting, perspective, board color and devices. None is acquired yet.
A source held out from training can measure that source's shift; it cannot establish arbitrary
Internet-photo robustness. Annotate shared classes consistently and report unsupported classes.

## Compatibility and quality gate

Design the product path as PCB/domain compatibility → inspectability → surface detector.
Recognize non-PCB images and unsupported assembled-board/domain images separately.
Return actionable rejection or uncertainty; do not convert low detector confidence into a
quality score. Use blur, glare, usable trace detail, perspective and board coverage as
measurable inputs, with expert inspectability labels and calibrated rejection thresholds.

Collect negatives and difficult valid inputs for this gate. Report false acceptance, false
rejection and defect recall after rejection, stratified by domain. Synthetic blur/lighting
augmentation belongs only in training and does not replace real difficult-image evaluation.
No calibrated classifier, score or rejection rule is implemented in this slice.

## User contributions and model promotion

Inspection upload alone grants no training consent. Keep optional training contribution consent,
rights declaration and consent version separate from service storage. Route low-confidence,
uncertain and sampled high-confidence cases for human review; model predictions are suggestions.
Only consented, reviewed labels with provenance may enter a new training manifest. Support
retention/deletion and withdrawal rules; exclude user data from frozen benchmarks.

Model promotion requires per-class AP/recall and confidence intervals by independent group,
false positives on clean boards, compatibility errors, latency/memory at target resolution,
source/domain breakdowns, artifact/label-map hashes and an approved model/framework license.
Choose numerical acceptance thresholds from the intended workflow and validation evidence;
do not present the demo thresholds as calibrated. Store runs and promotion evidence in MLflow.

## Next executable slices

1. Review PCB-Defect board/template groups and completeness; create the six-class grouped manifest.
2. Obtain PCB-IND v4 through the cited original deposit and reconcile classes.json with samples.
3. Add provenance/coverage support to composite manifests and implement tested COCO normalization.
4. Freeze independent evaluation sets; run the six-class baseline, then controlled multi-source
   experiments. Export the approved model with its exact supported-label contract.
5. Implement/calibrate compatibility, consent and human-review flows before enabling their claims.

Reproduce the current acquisition audit using [data/README.md](../data/README.md).
Measured evidence is in [data/audits/2026-09-08](../data/audits/2026-09-08).
