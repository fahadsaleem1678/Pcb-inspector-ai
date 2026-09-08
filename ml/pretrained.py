"""Explicit acquisition and local verification of the reviewed research initialization."""

import argparse
from pathlib import Path

from ml.data import file_hash

WEIGHT_ID = "FasterRCNN_MobileNet_V3_Large_320_FPN_Weights.COCO_V1"
URL = "https://download.pytorch.org/models/fasterrcnn_mobilenet_v3_large_320_fpn-907ea3f9.pth"
SHA256 = "907ea3f91ff92242bc1baea8049276a3e76bca48ce7560bd268cc029f37977b5"
REVIEW = Path(__file__).with_name("PRETRAINED.md")


def verify_weights(path):
    path = Path(path)
    if file_hash(path) != SHA256:
        raise ValueError("Initial weight checksum does not match reviewed COCO_V1 artifact")
    return {
        "id": WEIGHT_ID,
        "source_url": URL,
        "sha256": SHA256,
        "local_path": str(path.resolve()),
        "review_sha256": file_hash(REVIEW),
        "review_scope": "local research; public distribution approval unresolved",
    }


def acquire(path):
    # This separate command is the only network path; training/evaluation stay offline.
    import torch

    path = Path(path)
    if path.exists():
        return verify_weights(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.hub.download_url_to_file(URL, str(path), hash_prefix=SHA256, progress=True)
    return verify_weights(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(acquire(args.output))


if __name__ == "__main__":
    main()
