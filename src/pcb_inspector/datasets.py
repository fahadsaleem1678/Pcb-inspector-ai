"""Validate dataset provenance, annotation integrity and split leakage before training."""

import argparse
import hashlib
import json
import warnings
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Literal, Self

from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from pcb_inspector.schemas import BoundingBox

Purpose = Literal["research", "public_demo", "commercial"]
Split = Literal["train", "validation", "test"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DatasetLicense(StrictModel):
    name: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    allowed_uses: list[Purpose]
    reviewed_by: str = Field(min_length=1)
    reviewed_on: date


class Annotation(StrictModel):
    class_id: int = Field(ge=0)
    bbox: BoundingBox


class Sample(StrictModel):
    image: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    group_id: str = Field(min_length=1)
    split: Split
    annotations: list[Annotation]


class DatasetManifest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    source_url: HttpUrl
    source_revision: str = Field(min_length=1)
    license: DatasetLicense
    classes: list[str] = Field(min_length=1)
    samples: list[Sample] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_classes(self) -> Self:
        if len(self.classes) != len(set(self.classes)) or any(
            not name.strip() for name in self.classes
        ):
            raise ValueError("Class names must be unique and nonblank")
        return self


class Issue(StrictModel):
    severity: Literal["error", "review"]
    code: str
    message: str
    images: list[str] = Field(default_factory=list)


class ValidationReport(StrictModel):
    dataset: str
    version: str
    purpose: Purpose
    manifest_sha256: str
    valid: bool
    ready_for_training: bool
    sample_count: int
    max_image_pixels: int = 20_000_000
    split_counts: dict[str, int]
    class_counts: dict[str, int]
    split_class_counts: dict[str, dict[str, int]]
    issues: list[Issue]


def contained(root: Path, relative: str) -> Path:
    path = Path(relative)
    resolved = (root / path).resolve()
    if (
        path.is_absolute()
        or not resolved.is_relative_to(root.resolve())
        or resolved == root.resolve()
    ):
        raise ValueError("Dataset paths must be relative and stay within the dataset root")
    return resolved


def grouped_split(group_ids: list[str], seed: str = "pcb-v1") -> dict[str, Split]:
    """Assign complete groups deterministically; never call again to revise a frozen test set."""
    unique = sorted(
        set(group_ids), key=lambda group: hashlib.sha256(f"{seed}\0{group}".encode()).hexdigest()
    )
    if len(unique) < 3:
        raise ValueError("At least three independent groups are required")
    validation_count = max(1, round(len(unique) * 0.15))
    test_count = max(1, round(len(unique) * 0.15))
    return {
        group: "test"
        if index < test_count
        else "validation"
        if index < test_count + validation_count
        else "train"
        for index, group in enumerate(unique)
    }


def validate_dataset(
    manifest_path: Path,
    root: Path,
    purpose: Purpose = "research",
    *,
    max_image_pixels: int = 20_000_000,
) -> ValidationReport:
    if not 1 <= max_image_pixels <= 40_000_000:
        raise ValueError("Offline image limit must be between 1 and 40,000,000 pixels")
    raw_manifest = manifest_path.read_bytes()
    manifest = DatasetManifest.model_validate_json(raw_manifest)
    issues: list[Issue] = []

    def issue(code: str, message: str, *images: str, review: bool = False) -> None:
        issues.append(
            Issue(
                severity="review" if review else "error",
                code=code,
                message=message,
                images=list(images),
            )
        )

    if purpose not in manifest.license.allowed_uses:
        issue("usage_not_permitted", f"Recorded license review does not permit {purpose}")
    if manifest.license.reviewed_on > date.today():
        issue("invalid_review_date", "License review cannot be dated in the future")
    try:
        evidence = contained(root, manifest.license.evidence)
        if not evidence.is_file() or evidence.stat().st_size == 0:
            issue("missing_license_evidence", "License evidence must be a nonempty local file")
    except ValueError as exc:
        issue("unsafe_license_path", str(exc))

    split_counts: Counter[str] = Counter()
    class_counts: Counter[str] = Counter()
    split_classes: dict[str, Counter[str]] = {
        split: Counter() for split in ("train", "validation", "test")
    }
    groups: dict[str, set[str]] = defaultdict(set)
    paths: set[Path] = set()
    byte_hashes: dict[str, Sample] = {}
    pixel_hashes: dict[str, Sample] = {}
    perceptual: dict[str, list[tuple[int, Sample]]] = defaultdict(list)
    for sample in manifest.samples:
        split_counts[sample.split] += 1
        groups[sample.group_id].add(sample.split)
        for annotation in sample.annotations:
            if annotation.class_id >= len(manifest.classes):
                issue(
                    "unknown_class",
                    "Annotation class ID is absent from the class map",
                    sample.image,
                )
                continue
            name = manifest.classes[annotation.class_id]
            class_counts[name] += 1
            split_classes[sample.split][name] += 1
            if annotation.bbox.x2 > sample.width or annotation.bbox.y2 > sample.height:
                issue("out_of_bounds", "Annotation exceeds declared image dimensions", sample.image)
        try:
            image_path = contained(root, sample.image)
            if image_path in paths:
                issue("duplicate_path", "Image path appears more than once", sample.image)
            paths.add(image_path)
            with image_path.open("rb") as stream:
                actual_hash = hashlib.file_digest(stream, "sha256").hexdigest()
            if actual_hash != sample.sha256:
                issue("checksum_mismatch", "Image differs from the manifest checksum", sample.image)
            if actual_hash in byte_hashes:
                previous = byte_hashes[actual_hash]
                issue(
                    "duplicate_bytes",
                    "Identical image bytes appear more than once",
                    previous.image,
                    sample.image,
                )
            else:
                byte_hashes[actual_hash] = sample
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(image_path) as image:
                    if image.format not in {"JPEG", "PNG"}:
                        raise ValueError("Only JPEG and PNG dataset images are supported")
                    if image.width * image.height > max_image_pixels:
                        raise ValueError(
                            f"Image exceeds the {max_image_pixels:,}-pixel offline decode limit"
                        )
                    if getattr(image, "n_frames", 1) != 1 or image.getexif().get(274, 1) != 1:
                        raise ValueError(
                            "Normalize animation/orientation and labels before validation"
                        )
                    if image.size != (sample.width, sample.height):
                        issue(
                            "dimension_mismatch",
                            "Decoded dimensions differ from the manifest",
                            sample.image,
                        )
                    image.load()
                    pixels = image.convert("RGB")
                    digest = hashlib.sha256(
                        f"{pixels.width}x{pixels.height}:".encode() + pixels.tobytes()
                    ).hexdigest()
                    if digest in pixel_hashes and actual_hash not in {
                        pixel_hashes[digest].sha256,
                    }:
                        issue(
                            "duplicate_pixels",
                            "Decoded image is duplicated in another encoding",
                            pixel_hashes[digest].image,
                            sample.image,
                        )
                    pixel_hashes.setdefault(digest, sample)
                    thumbnail = pixels.convert("L").resize((8, 8))
                    levels = list(thumbnail.tobytes())
                    mean = sum(levels) / len(levels)
                    signature = sum(
                        (1 << index) for index, level in enumerate(levels) if level >= mean
                    )
                    # Flag likely leakage for review; this coarse hash is not proof of duplication.
                    for other_split, values in perceptual.items():
                        if other_split == sample.split:
                            continue
                        for other_hash, previous in values:
                            if (signature ^ other_hash).bit_count() <= 4:
                                issue(
                                    "possible_visual_leakage",
                                    "Similar cross-split thumbnails need human review",
                                    previous.image,
                                    sample.image,
                                    review=True,
                                )
                    perceptual[sample.split].append((signature, sample))
        except (
            OSError,
            ValueError,
            SyntaxError,
            UnidentifiedImageError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as exc:
            issue("image_unreadable", str(exc), sample.image)

    for group, splits in groups.items():
        if len(splits) > 1:
            issue("group_leakage", f"Group {group!r} spans multiple splits")
    for split in ("train", "validation", "test"):
        if split_counts[split] == 0:
            issue("empty_split", f"The {split} split has no images")
        for name in manifest.classes:
            if split_classes[split][name] == 0:
                issue(
                    "missing_class_coverage", f"{name!r} has no annotations in {split}", review=True
                )
    return ValidationReport(
        dataset=manifest.name,
        version=manifest.version,
        purpose=purpose,
        manifest_sha256=hashlib.sha256(raw_manifest).hexdigest(),
        valid=not any(item.severity == "error" for item in issues),
        ready_for_training=not issues,
        sample_count=len(manifest.samples),
        max_image_pixels=max_image_pixels,
        split_counts=dict(split_counts),
        class_counts={name: class_counts[name] for name in manifest.classes},
        split_class_counts={
            split: {name: counts[name] for name in manifest.classes}
            for split, counts in split_classes.items()
        },
        issues=issues,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a PCB dataset before training")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--purpose", choices=["research", "public_demo", "commercial"], default="research"
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--max-image-pixels",
        type=int,
        default=20_000_000,
        help="Offline decode bound (maximum 40,000,000); does not affect API upload limits",
    )
    args = parser.parse_args()
    try:
        report = validate_dataset(
            args.manifest, args.root, args.purpose, max_image_pixels=args.max_image_pixels
        )
        output = report.model_dump_json(indent=2)
    except (ValueError, OSError) as exc:
        print(
            json.dumps({"valid": False, "ready_for_training": False, "error": str(exc)}, indent=2)
        )
        raise SystemExit(2) from exc
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    print(output)
    raise SystemExit(0 if report.ready_for_training else 1)


if __name__ == "__main__":
    main()
