# Internet dataset discovery - 2026-09-14

Purpose: find normal PCB examples and industrial camera data for the flagged-board workflow.
Discovery does not approve a new dataset release, class mapping or production model.

| Source | Verified availability / declared content | Fit and limitation |
| --- | --- | --- |
| [MeiweiPCB](https://github.com/youtang1993/MeiweiPCB) | Downloaded 969 normal and 969 defect images, all decoding as 220x220; COCO has one generic defect category | Best immediate candidate for normal patches/binary surface inspection; not a six-class or whole-board benchmark |
| [DsPCBSD+](https://figshare.com/articles/dataset/DsPCBSD_/24970329) | Publisher reports 10,259 images, 20,276 boxes and nine surface classes; Figshare API exposes a 128,541,608-byte ZIP and CC BY 4.0 | Strong multi-class industrial source; defect crops, not a verified clean-board set |
| [VisA](https://github.com/amazon-science/spot-diff) | Official table lists 4,016 normal and 400 anomalous PCB images across four subsets; CC BY 4.0 dataset license | Useful separate assembled-PCB anomaly benchmark; outside current bare-board surface scope |
| [PCB-IND](https://zenodo.org/records/19723114) | Zenodo API now accessible: PCB-IND_v4.zip, 101,336,845 bytes, CC BY 4.0 | Industrial AOI candidate; previously identified repository/paper class conflict still unresolved |

## MeiweiPCB: measured local acquisition

Repository revision: c19045cec8010a7576251fb24ef0c03c1c0ebefb. Downloaded images.zip,
images_nor.zip and annotations_coco.zip into ignored data/raw/meiwei-discovery-c19045ce.
Each archive matched the Git tree blob hash. SHA256 values and measured counts are recorded
in [discovery evidence](dataset-discovery-2026-09-14.json). No archive content was executed.

All 1,938 images decoded. There is one duplicate decoded image within the defect collection
and three within the normal collection; no identical decoded images crossed those conditions.
This is exact-duplicate checking, not near-duplicate or physical-board independence review.
The COCO files contain 581 train / 194 validation / 194 test images, with 777 / 256 / 242
annotations respectively. Their sole category is ID 1, name "1". No model inference was run.

The author [README](https://github.com/youtang1993/MeiweiPCB) describes industrial line-scan
capture and normal/OK counterparts, but says the complete dataset will be released later.
The current archive count is 969 images per condition; do not replace this measured count
with the 939 defect images quoted by some papers. The repository includes
[Apache-2.0](https://github.com/youtang1993/MeiweiPCB/blob/master/LICENSE); dataset-specific
provenance and applicability still need review before a production release.

These are author-labeled normal patches, not independently certified clean full boards.
Before use: inspect normal/defect pairing, near duplicates and source grouping; retain all
related views in one split; preserve an untouched evaluation partition; review representative
normal examples and confirm rights. Do not infer six-class labels from a generic defect box.

## DsPCBSD+: acquired and audited

The [author paper](https://www.nature.com/articles/s41597-024-03656-8) describes actual etched
PCB defects captured by industrial AOI line-scan cameras and nine classes: short, spur,
spurious copper, open, mouse bite, hole breakout, conductor scratch, conductor foreign object,
and base-material foreign object. Capture starts from 226x226 candidate crops. These class
names do not fully match the current six-class contract; missing pad is not established by
renaming hole breakout. Retain source labels and review mapping before mixing datasets.

[Figshare file](https://ndownloader.figshare.com/files/44069552): DsPCBSD+.zip,
128,541,608 bytes; publisher MD5 508334b65bdaea7336f4c1b5d5a80a81.
DOI: 10.6084/m9.figshare.24970329.v1. Archive subsequently downloaded and verified against
the publisher size and MD5. See [candidate audit](dataset-candidate-audit.md) for measured
counts, split checks and bounded annotation correction proposals.

## Other sources

VisA's normal PCB images are attractive for anomaly research, but its PCB subsets include
components. Keep this as a separate V2/domain experiment rather than silently treating it
as representative clean data for bare-board surface inspection. The official source provides
[dataset licensing](https://github.com/amazon-science/spot-diff/blob/main/LICENSE-DATASET)
and [download](https://amazon-visual-anomaly.s3.us-west-2.amazonaws.com/VisA_20220922.tar).
No VisA images were downloaded.

PCB-IND metadata is available again through the [Zenodo API](https://zenodo.org/api/records/19723114).
Archive MD5: 1325f8dffeb73bef4db34fbd22b31ec5. The archive has not yet been downloaded or its
internal classes.json reconciled with the conflicting dictionaries already recorded in
dataset-v1-spec.md. Metadata access is not proof of successful archive acquisition.

## Recommended next work

Audit Meiwei normal/defect pairing and grouping first, then acquire/check DsPCBSD+ for a
separate source-specific training comparison. These sources can improve research coverage;
neither substitutes for full-board images from the eventual camera setup when measuring
production board escapes and review workload. No frozen manifest, labels, thresholds or
production model settings changed in this task.
