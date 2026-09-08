"""Reproduce PCB-Defect review features and build its frozen research manifest.

Run 'review' before 'build'. Source images are copied without pixel transformations.
"""

import argparse
import hashlib
import io
import itertools
import json
import math
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

from PIL import Image, ImageOps

from pcb_inspector.datasets import DatasetManifest, contained

ARCHIVE_SHA256 = "a5fb17e7009f96ffdb833cd9309b36da775545c8cc36a6dca3a8e9b4fbcb5f2a"
LABELS = ["missing_pad", "mouse_bite", "open_circuit", "short_circuit", "spur", "spurious_copper"]
PREFIX = "PCB_Defect/images/"
COSINES = [[math.cos((2 * x + 1) * k * math.pi / 64) for x in range(32)] for k in range(8)]


def encoded(value):
    return (json.dumps(value, indent=2, ensure_ascii=True) + "\n").encode("utf-8")


def sha256(value):
    return hashlib.sha256(value).hexdigest()


def frozen_write(path, body):
    """Never silently replace an existing release or its source bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != body:
            raise ValueError(f"Refusing to change frozen artifact: {path}")
        return
    with path.open("xb") as stream:
        stream.write(body)


def source(archive_path):
    with archive_path.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != ARCHIVE_SHA256:
            raise ValueError("Source archive checksum does not match the pinned release")
    with zipfile.ZipFile(archive_path) as archive:
        coco = json.loads(archive.read("PCB_Defect/annotation/_annotations.coco.json"))
    expected = {
        str(i + 1): label.replace("short_circuit", "short") for i, label in enumerate(LABELS)
    }
    actual = {str(c["id"]): c["name"] for c in coco["categories"] if c["id"] != 0}
    if actual != expected:
        raise ValueError("Source category dictionary differs from the reviewed six-class map")
    return coco


def family(record):
    original = record.get("extra", {}).get("name", "")
    match = re.fullmatch(r"(\d+)-\d+-\d+\.png", original)
    if not match:
        raise ValueError(f"Missing or unexpected original-name provenance: {original}")
    return match[1]


def average_hash(image):
    levels = list(image.convert("L").resize((8, 8)).tobytes())
    mean = sum(levels) / len(levels)
    return sum((v >= mean) << i for i, v in enumerate(levels))


def perceptual_hash(image):
    pixels = list(image.convert("L").resize((32, 32)).tobytes())
    rows = [
        [sum(pixels[y * 32 + x] * COSINES[k][x] for x in range(32)) for k in range(8)]
        for y in range(32)
    ]
    values = [
        sum(rows[y][kx] * COSINES[ky][y] for y in range(32)) for ky in range(8) for kx in range(8)
    ][1:]
    threshold = median(values)
    return sum((v > threshold) << i for i, v in enumerate(values))


def variants(image):
    for mirror in (False, True):
        base = ImageOps.mirror(image) if mirror else image
        for angle in (0, 90, 180, 270):
            yield base.rotate(angle, expand=True)


def review(archive_path, output):
    coco = source(archive_path)
    output.mkdir(parents=True, exist_ok=True)
    features = []
    with zipfile.ZipFile(archive_path) as archive:
        for record in sorted(coco["images"], key=lambda r: r["file_name"]):
            with Image.open(io.BytesIO(archive.read(PREFIX + record["file_name"]))) as image:
                image.thumbnail((300, 250))
                thumb = image.convert("RGB")
            hashes = [average_hash(im) for im in variants(thumb)]
            # The visual-review JPEG is also the pHash input; keep this codec setting pinned.
            buffer = io.BytesIO()
            thumb.save(buffer, format="JPEG", quality=80)
            body = buffer.getvalue()
            (output / record["file_name"]).write_bytes(body)
            with Image.open(io.BytesIO(body)) as jpeg:
                phashes = [perceptual_hash(im) for im in variants(jpeg)]
            features.append(
                {
                    "image": record["file_name"],
                    "original": record["extra"]["name"],
                    "family": family(record),
                    "hashes": hashes,
                    "phashes": phashes,
                }
            )
    pairs = []
    for i, a in enumerate(features):
        for b in features[i + 1 :]:
            if a["family"] == b["family"]:
                continue
            distance = min((a["phashes"][0] ^ h).bit_count() for h in b["phashes"])
            average = min((a["hashes"][0] ^ h).bit_count() for h in b["hashes"])
            if distance <= 12 or average <= 8:
                pairs.append(
                    {
                        "a": a["image"],
                        "b": b["image"],
                        "family_a": a["family"],
                        "family_b": b["family"],
                        "phash_distance": distance,
                        "ahash_distance": average,
                    }
                )
    (output / "features.json").write_bytes(encoded(features))
    (output / "candidates.json").write_bytes(encoded(pairs))
    print(json.dumps({"images": len(features), "candidates": len(pairs)}))
    return pairs


def make_groups(records, decisions):
    families = {family(r) for r in records}
    parent = {f: f for f in families}

    def find(item):
        while parent[item] != item:
            item = parent[item]
        return item

    for decision in decisions:
        if decision["decision"] not in {"merge_conservatively", "different_layout"}:
            raise ValueError("Every candidate needs a recorded decision")
        a, b = decision["candidate"]["family_a"], decision["candidate"]["family_b"]
        if a not in families or b not in families:
            raise ValueError("Unknown reviewed family")
        if decision["decision"] == "merge_conservatively":
            a, b = find(a), find(b)
            parent[max(a, b)] = min(a, b)
    return {f: "pcb-defect-family-" + find(f) for f in sorted(families)}


def choose_holdout(group_stats, total, count, excluded):
    available = sorted(set(group_stats) - excluded)
    candidates = []
    for chosen in itertools.combinations(available, count):
        selected = Counter()
        for group in chosen:
            selected.update(group_stats[group])
        if any(selected[str(i)] == 0 for i in range(6)):
            continue
        remaining = Counter()
        for group in set(available) - set(chosen):
            remaining.update(group_stats[group])
        if any(remaining[str(i)] == 0 for i in range(6)):
            continue
        # Metadata-only stratification. No model outputs, scores, or seed search.
        score = sum((selected[key] / total[key] - 0.15) ** 2 for key in total)
        tie = sha256("|".join(chosen).encode())
        candidates.append((score, tie, chosen))
    if not candidates:
        raise ValueError("Cannot preserve class coverage in independent holdout groups")
    return min(candidates)[2]


def build(archive_path, review_path, features_root, dataset_root, manifest_path, release_root):
    coco = source(archive_path)
    decisions = json.loads(review_path.read_text(encoding="utf-8"))
    if decisions["archive_sha256"] != ARCHIVE_SHA256:
        raise ValueError("Grouping review is for another source archive")
    candidates = json.loads((features_root / "candidates.json").read_text(encoding="utf-8"))
    if [d["candidate"] for d in decisions["decisions"]] != candidates:
        raise ValueError("Reproduced candidates differ from the completed grouping review")
    groups = make_groups(coco["images"], decisions["decisions"])
    annotations = defaultdict(list)
    for annotation in coco["annotations"]:
        category = annotation["category_id"]
        if category not in range(1, 7):
            raise ValueError("Unmapped source annotation class")
        x, y, width, height = annotation["bbox"]
        annotations[annotation["image_id"]].append(
            {
                "class_id": category - 1,
                "bbox": {"x1": x, "y1": y, "x2": x + width, "y2": y + height},
            }
        )
    stats = defaultdict(Counter)
    for record in coco["images"]:
        group = groups[family(record)]
        stats[group]["images"] += 1
        stats[group].update(str(a["class_id"]) for a in annotations[record["id"]])
    total = Counter()
    for counts in stats.values():
        total.update(counts)
    holdout_count = max(1, round(len(stats) * 0.15))
    test = set(choose_holdout(stats, total, holdout_count, set()))
    validation = set(choose_holdout(stats, total, holdout_count, test))
    assignment = {
        group: "test" if group in test else "validation" if group in validation else "train"
        for group in sorted(stats)
    }
    evidence = {
        "source": "https://data.mendeley.com/datasets/vdj74sngvn/1",
        "doi": "10.17632/vdj74sngvn.1",
        "archive_sha256": ARCHIVE_SHA256,
        "declared_license": "CC BY 4.0",
        "embedded_coco_licenses": coco["licenses"],
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "attribution": "Rashid, Ullah, Isfara, Ahmed, Mian and Shalehin; PCB-Defect V1 (2025).",
        "reviewed_by": "Codex (source declarations and embedded license review)",
        "reviewed_on": "2026-09-08",
        "review_scope": "Research preparation; no legal or annotation-quality certification.",
        "modifications": (
            "Images unchanged. COCO xywh converted to xyxy; classes remapped; grouped splits."
        ),
    }
    samples, lineage = [], []
    with zipfile.ZipFile(archive_path) as archive:
        for record in sorted(coco["images"], key=lambda r: r["file_name"]):
            relative = "images/" + record["file_name"]
            data = archive.read(PREFIX + record["file_name"])
            group = groups[family(record)]
            samples.append(
                {
                    "image": relative,
                    "sha256": sha256(data),
                    "width": record["width"],
                    "height": record["height"],
                    "group_id": group,
                    "split": assignment[group],
                    "annotations": annotations[record["id"]],
                }
            )
            lineage.append(
                {
                    "image": relative,
                    "source_image_id": record["id"],
                    "source_name": record["extra"]["name"],
                    "source_family": family(record),
                    "group_id": group,
                    "split": assignment[group],
                }
            )
    manifest = {
        "schema_version": "1.0",
        "name": "pcb-defect-surface",
        "version": "1.0.0",
        "source_url": evidence["source"],
        "source_revision": f"V1; sha256:{ARCHIVE_SHA256}",
        "license": {
            "name": "CC BY 4.0",
            "evidence": "license-evidence.json",
            "allowed_uses": ["research"],
            "reviewed_by": evidence["reviewed_by"],
            "reviewed_on": evidence["reviewed_on"],
        },
        "classes": LABELS,
        "samples": samples,
    }
    DatasetManifest.model_validate(manifest)
    body = encoded(manifest)
    release = {
        "version": "1.0.0",
        "frozen_on": "2026-09-08",
        "purpose": "research",
        "manifest_sha256": sha256(body),
        "source_archive_sha256": ARCHIVE_SHA256,
        "grouping_review_sha256": sha256(review_path.read_bytes()),
        "license_evidence_sha256": sha256(encoded(evidence)),
        "split_algorithm": "metadata-class-and-image-stratification-v1",
        "group_assignment": assignment,
        "family_to_group": groups,
        "group_counts": {g: dict(c) for g, c in sorted(stats.items())},
        "lineage": lineage,
        "production_ready": False,
        "limitations": [
            "Conservative provenance/layout groups; "
            "physical board identities not supplied by authors.",
            "Hash screening and visual review do not rule out all cropped/modified relatives.",
            "Original labels preserved; annotation completeness not independently certified.",
            "No clean-board negatives or external camera holdout; no public performance claim.",
        ],
    }
    # Check frozen metadata BEFORE copying any source images.
    for path, content in [
        (manifest_path, body),
        (release_root / "release.json", encoded(release)),
        (dataset_root / "license-evidence.json", encoded(evidence)),
    ]:
        if path.exists() and path.read_bytes() != content:
            raise ValueError(f"Refusing to change frozen artifact: {path}")
    with zipfile.ZipFile(archive_path) as archive:
        for sample in samples:
            frozen_write(
                contained(dataset_root, sample["image"]),
                archive.read(PREFIX + Path(sample["image"]).name),
            )
    frozen_write(dataset_root / "license-evidence.json", encoded(evidence))
    frozen_write(manifest_path, body)
    frozen_write(release_root / "release.json", encoded(release))
    print(
        json.dumps(
            {
                "manifest_sha256": sha256(body),
                "groups": len(stats),
                "split_images": dict(Counter(s["split"] for s in samples)),
                "split_groups": dict(Counter(assignment.values())),
            },
            indent=2,
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["review", "build"])
    parser.add_argument("--archive", type=Path, default=Path("data/raw/source-audit/defect.zip"))
    parser.add_argument(
        "--review-root", type=Path, default=Path("data/interim/pcb-defect-v1-review")
    )
    parser.add_argument(
        "--decisions", type=Path, default=Path("data/releases/pcb-defect-v1/group-review.json")
    )
    parser.add_argument("--root", type=Path, default=Path("data/processed/pcb-defect-v1"))
    parser.add_argument(
        "--manifest", type=Path, default=Path("data/manifests/pcb-defect-v1.0.json")
    )
    parser.add_argument("--release-root", type=Path, default=Path("data/releases/pcb-defect-v1"))
    args = parser.parse_args()
    if args.action == "review":
        review(args.archive, args.review_root)
    else:
        build(
            args.archive,
            args.decisions,
            args.review_root,
            args.root,
            args.manifest,
            args.release_root,
        )


if __name__ == "__main__":
    main()
