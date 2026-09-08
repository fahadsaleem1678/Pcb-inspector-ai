# COCO initialization provenance review

Reviewed 2026-09-08 for an explicitly requested local research experiment. This records
provenance and limitations; it is not a legal determination or public distribution approval.

## Artifact

- Publisher: PyTorch / Torchvision; enum
  `FasterRCNN_MobileNet_V3_Large_320_FPN_Weights.COCO_V1` in installed Torchvision 0.28.0.
- [Official weight file](https://download.pytorch.org/models/fasterrcnn_mobilenet_v3_large_320_fpn-907ea3f9.pth), 77,844,807 bytes.
- SHA-256: `907ea3f91ff92242bc1baea8049276a3e76bca48ce7560bd268cc029f37977b5`.
  Initial acquisition checked publisher filename prefix `907ea3f9`; subsequent acquisitions
  and every training initialization check the full locally recorded hash.
- [Versioned factory source](https://github.com/pytorch/vision/blob/v0.28.0/torchvision/models/detection/faster_rcnn.py)
  and [official model documentation](https://docs.pytorch.org/vision/0.28/models/generated/torchvision.models.detection.fasterrcnn_mobilenet_v3_large_320_fpn.html).
- [Publisher training description](https://pytorch.org/blog/ml-models-torchvision-v0.9/)
  identifies COCO train2017. COCO validation scores are unrelated to PCB accuracy.

## Terms reviewed

[Torchvision's pretrained-model notice](https://github.com/pytorch/vision#pre-trained-model-license)
says weight terms may derive from training datasets; the library's BSD license is not
blanket clearance for the weights. [COCO's published terms](https://raw.githubusercontent.com/cocodataset/cocodataset.github.io/master/dataset/termsofuse.htm)
license annotations under CC BY 4.0 and separately identify third-party image copyright and
Flickr terms. They do not establish one blanket license for all training images or derived
checkpoints. Upstream backbone pretraining provenance and downstream distribution rights
need further review before a public product release.

Only the checkpoint is downloaded for local research. Weights and fine-tuned checkpoints
remain ignored, are not vendored into Git or Docker, and are not enabled in the website.
All resulting artifacts remain `promotion_eligible=false`. No claim of commercially cleared
weights or public inference approval follows from this review.

## Loading contract

Training takes an explicit local `--initial-weights` path; the training and evaluation
commands do not fetch weights. Load uses `weights_only=True`, full SHA verification and
strict state matching against a 91-output COCO model. Preserve FrozenBatchNorm2d in the
backbone, then replace only the class/box predictor with six classes plus background.
All six backbone stages remain trainable, unlike the upstream pretrained factory default
of three. Frozen normalization statistics stay fixed. RPN/FPN/box-head weights transfer.
Evaluation recreates the saved normalization topology without needing the initial artifact.
The scratch path keeps ordinary BatchNorm2d and remains compatible with earlier runs.
