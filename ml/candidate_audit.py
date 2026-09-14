"""Read-only source-archive audits. Never creates a training release or changes source splits."""

import argparse
import hashlib
import io
import json
import math
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

from PIL import Image


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def member_bytes(archive, name, limit=20_000_000):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError("Unsafe archive member")
    if archive.getinfo(name).file_size > limit:
        raise ValueError("Archive member exceeds size limit")
    return archive.read(name)


def fingerprint(raw):
    with Image.open(io.BytesIO(raw)) as image:
        if image.width * image.height > 1_000_000:
            raise ValueError("Unexpected candidate image size")
        image.load()
        rgb = image.convert("RGB")
        thumb = list(rgb.convert("L").resize((9, 8), Image.Resampling.LANCZOS).tobytes())
        bits = 0
        for y in range(8):
            for x in range(8):
                bits = (bits << 1) | (thumb[y * 9 + x] > thumb[y * 9 + x + 1])
        return {
            "width": rgb.width,
            "height": rgb.height,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "pixel_sha256": hashlib.sha256(str(rgb.size).encode() + rgb.tobytes()).hexdigest(),
            "dhash": bits,
        }


def read_coco(document, archive, prefix, split):
    classes = {c["id"]: c["name"] for c in document["categories"]}
    if len(classes) != len(document["categories"]):
        raise ValueError("Duplicate category IDs")
    images = {image["id"]: image for image in document["images"]}
    if len(images) != len(document["images"]):
        raise ValueError("Duplicate image IDs")
    annotations = defaultdict(list)
    issues = []
    seen = set()
    for a in document["annotations"]:
        if a["id"] in seen:
            issues.append({"code": "duplicate_annotation_id", "id": a["id"], "split": split})
        seen.add(a["id"])
        if a["image_id"] not in images or a["category_id"] not in classes:
            raise ValueError("Annotation references unknown image/category")
        box = a["bbox"]
        image = images[a["image_id"]]
        if (
            len(box) != 4
            or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in box)
            or min(box[:2]) < 0
            or min(box[2:]) <= 0
            or box[0] + box[2] > image["width"] + 1e-6
            or box[1] + box[3] > image["height"] + 1e-6
        ):
            issues.append(
                {
                    "code": "invalid_box",
                    "split": split,
                    "annotation_id": a["id"],
                    "file": image["file_name"],
                    "bbox": box,
                }
            )
        annotations[a["image_id"]].append(a)
    rows = []
    for image_id, image in images.items():
        name = image["file_name"]
        if PurePosixPath(name).name != name:
            raise ValueError("COCO filename must be a basename")
        member = prefix + name
        fp = fingerprint(member_bytes(archive, member))
        if (fp["width"], fp["height"]) != (image["width"], image["height"]):
            issues.append({"code": "dimension_mismatch", "file": name, "split": split})
        seen_boxes = set()
        for a in annotations[image_id]:
            key = (a["category_id"], *a["bbox"])
            if key in seen_boxes:
                issues.append({"code": "duplicate_box", "file": name, "split": split})
            seen_boxes.add(key)
        rows.append(
            {
                "file": name,
                "member": member,
                "split": split,
                **fp,
                "annotations": [
                    {"category_id": a["category_id"], "bbox": a["bbox"]}
                    for a in annotations[image_id]
                ],
            }
        )
    if len({r["file"] for r in rows}) != len(rows):
        raise ValueError("Duplicate filenames in split")
    return rows, classes, issues


def leakage(rows, near_distance=2, limit=100):
    groups = defaultdict(list)
    for row in rows:
        groups[row["pixel_sha256"]].append(row)
    duplicate_groups = [
        [{"file": r["file"], "split": r["split"]} for r in group]
        for group in groups.values()
        if len(group) > 1
    ]
    cross = [g for g in duplicate_groups if len({r["split"] for r in g}) > 1]
    count, candidates = 0, []
    # Exhaustive across-split 64-bit thumbnail comparison; heuristic, not proof of identity.
    for index, first in enumerate(rows):
        for second in rows[index + 1 :]:
            if first["split"] == second["split"] or first["pixel_sha256"] == second["pixel_sha256"]:
                continue
            distance = (first["dhash"] ^ second["dhash"]).bit_count()
            if distance <= near_distance:
                count += 1
                if len(candidates) < limit:
                    candidates.append(
                        {
                            "first": first["file"],
                            "first_split": first["split"],
                            "second": second["file"],
                            "second_split": second["split"],
                            "dhash_distance": distance,
                        }
                    )
    return {
        "duplicate_pixel_groups": duplicate_groups,
        "cross_split_duplicate_pixel_groups": cross,
        "near_duplicate_method": (
            f"64-bit dHash, original orientation, Hamming distance <={near_distance}"
        ),
        "near_duplicate_cross_split_pairs": count,
        "near_duplicate_candidates": candidates,
        "candidate_list_truncated": count > limit,
        "near_duplicate_is_proof_of_leakage": False,
    }


def statistics(rows, classes):
    counts = Counter(a["category_id"] for row in rows for a in row["annotations"])
    return {
        "images": len(rows),
        "annotations": sum(counts.values()),
        "annotation_empty_images": sum(not row["annotations"] for row in rows),
        "split_images": dict(Counter(row["split"] for row in rows)),
        "dimensions": dict(Counter(f"{r['width']}x{r['height']}" for r in rows)),
        "classes": {
            str(i): {"name": name, "annotations": counts[i]} for i, name in classes.items()
        },
    }


def audit_meiwei(root):
    rows, issues, classes = [], [], None
    paths = [root / name for name in ("images.zip", "images_nor.zip", "annotations_coco.zip")]
    with (
        zipfile.ZipFile(paths[0]) as images,
        zipfile.ZipFile(paths[1]) as normals,
        zipfile.ZipFile(paths[2]) as labels,
    ):
        for name in labels.namelist():
            if not name.endswith(".json"):
                continue
            split = "train" if "train" in name else "validation" if "val" in name else "test"
            batch, mapping, findings = read_coco(
                json.loads(member_bytes(labels, name)), images, "images/", split
            )
            if classes is not None and classes != mapping:
                raise ValueError("Class maps differ between splits")
            classes = mapping
            rows.extend(batch)
            issues.extend(findings)
        normal_rows = []
        pairs = []
        for row in rows:
            key = row["file"].removesuffix("_Cur.jpg")
            normal_name = key + "_Ref.jpg"
            member = "images_nor/" + normal_name
            normal_rows.append(
                {
                    "file": normal_name,
                    "member": member,
                    "split": row["split"],
                    **fingerprint(member_bytes(normals, member)),
                    "annotations": [],
                }
            )
            pairs.append(
                {
                    "defect": row["file"],
                    "normal": normal_name,
                    "source_split": row["split"],
                    "pair_key": key,
                }
            )
        listed = {r["member"] for r in normal_rows}
        available = {n for n in normals.namelist() if n.lower().endswith((".png", ".jpg"))}
        if listed != available:
            raise ValueError("Normal pairing is incomplete or has extra images")
    families = defaultdict(Counter)
    for row in rows:
        match = re.search(r"(10e[^_]+|TL\d+)", row["file"])
        families[match.group(1) if match else "unresolved"][row["split"]] += 1
    return {
        "source": "MeiweiPCB",
        "archive_sha256": {p.name: digest(p) for p in paths},
        "statistics": statistics(rows, classes),
        "issues": issues,
        "normal_images": len(normal_rows),
        "matched_filename_pairs": len(pairs),
        "normal_split_assignment": "Inherits matching Cur filename split for leakage audit only",
        "defect_leakage": leakage(rows),
        "normal_leakage": leakage(normal_rows),
        "filename_family_hints": {k: dict(v) for k, v in families.items()},
        "family_hints_are_verified_board_ids": False,
    }, {"defects": rows, "normals": normal_rows, "pairs": pairs}


def normalize_border_rounding(box, width, height, tolerance=0.02):
    """Propose a bounded border correction without modifying source annotations."""
    if (
        len(box) != 4
        or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in box)
        or min(box[2:]) <= 0
        or not all(math.isfinite(v) and v > 0 for v in (width, height))
        or not math.isfinite(tolerance)
        or not 0 <= tolerance <= 0.02
    ):
        raise ValueError("Invalid box, dimensions or tolerance")
    x, y, w, h = box
    right, bottom = x + w, y + h
    if max(0, -x, -y, right - width, bottom - height) > tolerance:
        raise ValueError("Box exceeds border-rounding tolerance")
    clipped = [max(0, x), max(0, y), min(width, right), min(height, bottom)]
    if clipped[2] <= clipped[0] or clipped[3] <= clipped[1]:
        raise ValueError("Clipping would erase box")
    if x >= 0 and y >= 0 and right <= width and bottom <= height:
        return list(box)
    return [clipped[0], clipped[1], clipped[2] - clipped[0], clipped[3] - clipped[1]]


def audit_dsp(archive_path):
    rows, issues, classes = [], [], None
    with zipfile.ZipFile(archive_path) as archive:
        for suffix, split in (("train2017", "train"), ("val2017", "validation")):
            document = json.loads(
                member_bytes(archive, f"Data_COCO/annotations/instances_{suffix}.json")
            )
            batch, mapping, findings = read_coco(document, archive, f"Data_COCO/{suffix}/", split)
            if classes is not None and classes != mapping:
                raise ValueError("Class maps differ between splits")
            classes = mapping
            rows.extend(batch)
            issues.extend(findings)
        # COCO and YOLO copies are alternate encodings, not independent samples.
        format_mismatch = []
        for row in rows:
            split = "train" if row["split"] == "train" else "val"
            raw = member_bytes(archive, f"Data_YOLO/images/{split}/{row['file']}")
            if hashlib.sha256(raw).hexdigest() != row["sha256"]:
                format_mismatch.append(row["file"])
    proposals, unnormalizable = [], []
    for row in rows:
        for index, annotation in enumerate(row["annotations"]):
            identity = {
                "file": row["file"],
                "split": row["split"],
                "annotation_index": index,
                "category_id": annotation["category_id"],
            }
            try:
                after = normalize_border_rounding(annotation["bbox"], row["width"], row["height"])
            except ValueError as error:
                unnormalizable.append({**identity, "reason": str(error)})
                continue
            if after != annotation["bbox"]:
                proposals.append(
                    {**identity, "before_xywh": annotation["bbox"], "after_xywh": after}
                )
    return {
        "source": "DsPCBSD+",
        "archive_sha256": digest(archive_path),
        "statistics": statistics(rows, classes),
        "issues": issues,
        "coco_yolo_image_byte_mismatches": format_mismatch,
        "border_normalization": {
            "max_allowed_overshoot_pixels": 0.02,
            "proposals": proposals,
            "unnormalizable": unnormalizable,
            "source_annotations_modified": False,
        },
        "leakage": leakage(rows),
    }, {"images": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", choices=("meiwei", "dsp"))
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Candidate audit output already exists")
    report, inventory = (
        audit_meiwei(args.input) if args.source == "meiwei" else audit_dsp(args.input)
    )
    report.update(
        {
            "schema_version": "1.0",
            "code_sha256": digest(__file__),
            "ready_for_training": False,
            "production_eligible": False,
            "test_inference_performed": False,
        }
    )
    args.output.mkdir(parents=True)
    inventory_text = json.dumps(inventory, indent=2, allow_nan=False) + "\n"
    report["inventory_sha256"] = hashlib.sha256(inventory_text.encode("utf-8")).hexdigest()
    for name, data in (("inventory.json", inventory), ("audit.json", report)):
        with (args.output / name).open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(data, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                "source": report["source"],
                "statistics": report["statistics"],
                "issues": len(report["issues"]),
                "output": str(args.output),
            }
        )
    )


if __name__ == "__main__":
    main()
