"""Source-preserving resize/tile views with explicit coordinate transforms."""

import hashlib
import json
from pathlib import Path

from PIL import Image

from pcb_inspector.datasets import DatasetManifest, contained


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_release(manifest_path, root, release_dir):
    """Verify frozen evidence and current image bytes before starting an experiment."""
    manifest = DatasetManifest.model_validate_json(Path(manifest_path).read_bytes())
    release = json.loads((Path(release_dir) / "release.json").read_text(encoding="utf-8"))
    validation = json.loads((Path(release_dir) / "validation.json").read_text(encoding="utf-8"))
    digest = file_hash(manifest_path)
    if digest != release["manifest_sha256"] or digest != validation["manifest_sha256"]:
        raise ValueError("Manifest differs from frozen release or validation evidence")
    if not validation["ready_for_training"] or validation["issues"]:
        raise ValueError("Frozen validation has unresolved gates")
    if "research" not in manifest.license.allowed_uses:
        raise ValueError("Manifest does not record research permission")
    if file_hash(Path(release_dir) / "group-review.json") != release["grouping_review_sha256"]:
        raise ValueError("Grouping review differs from release")
    if file_hash(contained(root, manifest.license.evidence)) != release["license_evidence_sha256"]:
        raise ValueError("License evidence differs from release")
    groups = {}
    for sample in manifest.samples:
        if sample.group_id in groups and groups[sample.group_id] != sample.split:
            raise ValueError("Group crosses splits")
        groups[sample.group_id] = sample.split
        if release["group_assignment"].get(sample.group_id) != sample.split:
            raise ValueError("Sample differs from frozen group assignment")
        path = contained(root, sample.image)
        if file_hash(path) != sample.sha256:
            raise ValueError(f"Source image checksum mismatch: {sample.image}")
        with Image.open(path) as image:
            if image.size != (sample.width, sample.height):
                raise ValueError(f"Source image dimensions differ: {sample.image}")
    return manifest, digest


def starts(length, size, overlap):
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError("Tile size must be positive and overlap smaller than tile size")
    if length <= size:
        return [0]
    result = list(range(0, length - size + 1, size - overlap))
    if result[-1] != length - size:
        result.append(length - size)
    return result


def windows(width, height, tile_size, overlap):
    if tile_size == 0:
        return [(0, 0, width, height)]
    return [
        (x, y, min(width, x + tile_size), min(height, y + tile_size))
        for y in starts(height, tile_size, overlap)
        for x in starts(width, tile_size, overlap)
    ]


def crop_annotations(annotations, window):
    x, y, right, bottom = window
    boxes, labels = [], []
    for annotation in annotations:
        box = annotation.bbox
        clipped = [max(x, box.x1), max(y, box.y1), min(right, box.x2), min(bottom, box.y2)]
        if clipped[2] > clipped[0] and clipped[3] > clipped[1]:
            boxes.append([clipped[0] - x, clipped[1] - y, clipped[2] - x, clipped[3] - y])
            # Torchvision uses 0 for background; manifest uses 0 for the first defect.
            labels.append(annotation.class_id + 1)
    return boxes, labels


class BoardViews:
    """All views inherit the source image split; empty tiles are retained."""

    def __init__(self, manifest, root, split, tile_size=0, overlap=0, image_limit=None):
        if split not in {"train", "validation", "test"}:
            raise ValueError("Unknown split")
        self.root = Path(root)
        self.samples = [sample for sample in manifest.samples if sample.split == split]
        if image_limit is not None:
            if image_limit < 1:
                raise ValueError("Image limit must be positive")
            self.samples = self.samples[:image_limit]
        if not self.samples:
            raise ValueError(f"No source images in {split}")
        self.views = [
            (index, window)
            for index, sample in enumerate(self.samples)
            for window in windows(sample.width, sample.height, tile_size, overlap)
        ]
        self.by_image = {
            index: [i for i, (source_index, _) in enumerate(self.views) if source_index == index]
            for index in range(len(self.samples))
        }

    def __len__(self):
        return len(self.views)

    def __getitem__(self, index):
        import torch
        from torchvision.transforms.functional import pil_to_tensor

        source_index, window = self.views[index]
        sample = self.samples[source_index]
        with Image.open(contained(self.root, sample.image)) as image:
            cropped = image.convert("RGB").crop(window)
        boxes, labels = crop_annotations(sample.annotations, window)
        target = {
            "boxes": torch.tensor(boxes, dtype=torch.float32).reshape(-1, 4),
            "labels": torch.tensor(labels, dtype=torch.int64),
            "image_id": torch.tensor(source_index),
        }
        return pil_to_tensor(cropped).float() / 255, target


def restore_boxes(boxes, window):
    """Torchvision restores resize coordinates to its input crop; add only the crop offset."""
    result = boxes.clone()
    result[:, [0, 2]] += window[0]
    result[:, [1, 3]] += window[1]
    return result
