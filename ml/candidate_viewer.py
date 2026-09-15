"""Build an offline visual review package from verified candidate source archives."""

import argparse
import json
import shutil
import zipfile
from contextlib import ExitStack
from pathlib import Path

from ml.candidate_audit import digest, fingerprint, member_bytes
from ml.candidate_decisions import FIELDS, load_packet, read_json
from ml.candidate_manifest import stable_id


def prepare_payload(packet, catalog, inventory, packet_hash):
    collections = (
        {"defect": inventory["defects"], "normal": inventory["normals"]}
        if packet["source"] == "MeiweiPCB"
        else {"defect": inventory["images"]}
    )
    rows = {}
    for condition, entries in collections.items():
        for row in entries:
            identity = stable_id("image", [packet["source"], condition, row["split"], row["file"]])
            if identity in rows:
                raise ValueError("Duplicate inventory image")
            rows[identity] = row
    members = {m["image_id"]: m for m in packet["members"]}
    if set(members) != set(rows):
        raise ValueError("Inventory and packet membership differ")
    cases, needed = [], set()
    for identity, case in sorted(catalog.items()):
        subject, kind = case["subject"], case["kind"]
        if kind == "pair":
            ids = [subject["defect_image_id"], subject["normal_image_id"]]
        elif kind == "near":
            ids = [subject["first"], subject["second"]]
        elif kind == "box":
            ids = [subject["image_id"]]
        elif kind == "class":
            ids = [
                key
                for key, row in sorted(rows.items())
                if any(
                    a["category_id"] == subject["source_category_id"] for a in row["annotations"]
                )
            ][:6]
        else:
            ids = []
        if any(i not in members for i in ids):
            raise ValueError("Case references unknown image")
        needed.update(ids)
        cases.append(
            {
                "case_id": identity,
                "kind": kind,
                "subject": subject,
                "image_ids": ids,
                "search": " ".join(rows[i]["file"] for i in ids),
            }
        )
    images = {}
    for identity in sorted(needed):
        member, row = members[identity], rows[identity]
        if any(
            member[k] != row[k]
            for k in ("file", "member", "sha256", "pixel_sha256", "width", "height")
        ):
            raise ValueError("Packet image differs from inventory")
        images[identity] = {
            **member,
            "asset": "images/" + identity + ".jpg",
            "annotations": row["annotations"],
        }
    return {
        "source": packet["source"],
        "packet_sha256": packet_hash,
        "cases": cases,
        "images": images,
        "fields": {
            kind: {key: sorted(values) for key, values in fields.items()}
            for kind, fields in FIELDS.items()
        },
    }


def script_json(value):
    return (
        json.dumps(value, allow_nan=False)
        .replace("<", "\\u003c")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def build(args):
    if args.output.exists():
        raise ValueError("Output exists; choose a new viewer directory")
    packet, catalog, packet_hash = load_packet(args.packet, args.summary)
    if (
        digest(args.inventory) != packet["binding"]["inventory_sha256"]
        or digest(args.audit) != packet["binding"]["audit_sha256"]
    ):
        raise ValueError("Inventory or audit hash mismatch")
    audit = read_json(args.audit)
    payload = prepare_payload(packet, catalog, read_json(args.inventory), packet_hash)
    with ExitStack() as stack:
        if packet["source"] == "MeiweiPCB":
            for name, expected in audit["archive_sha256"].items():
                if digest(args.raw / name) != expected:
                    raise ValueError("Source archive hash mismatch")
            archives = {
                condition: stack.enter_context(zipfile.ZipFile(args.raw / name))
                for condition, name in (("defect", "images.zip"), ("normal", "images_nor.zip"))
            }
        else:
            if digest(args.raw) != audit["archive_sha256"]:
                raise ValueError("Source archive hash mismatch")
            archives = {"defect": stack.enter_context(zipfile.ZipFile(args.raw))}
        # Verify all selected members before writing any package files.
        for image in payload["images"].values():
            raw = member_bytes(archives[image["condition"]], image["member"])
            fp = fingerprint(raw)
            if any(fp[k] != image[k] for k in ("sha256", "pixel_sha256", "width", "height")):
                raise ValueError("Source image hash or dimensions mismatch")
        args.output.mkdir(parents=True)
        (args.output / "images").mkdir()
        for image in payload["images"].values():
            (args.output / image["asset"]).write_bytes(
                member_bytes(archives[image["condition"]], image["member"])
            )
    here = Path(__file__).parent
    html = (here / "candidate_viewer.html").read_text(encoding="utf-8")
    (args.output / "index.html").write_text(
        html.replace("__CANDIDATE_DATA__", script_json(payload)), encoding="utf-8", newline="\n"
    )
    shutil.copyfile(here / "candidate_viewer.js", args.output / "candidate_viewer.js")
    summary = {
        "schema_version": "1.0",
        "source": packet["source"],
        "packet_sha256": packet_hash,
        "cases": len(payload["cases"]),
        "images": len(payload["images"]),
        "viewer_sha256": digest(args.output / "index.html"),
        "script_sha256": digest(args.output / "candidate_viewer.js"),
        "generator_sha256": digest(__file__),
        "ready_for_training": False,
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("packet", "summary", "inventory", "audit", "raw", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    print(json.dumps(build(parser.parse_args())))


if __name__ == "__main__":
    main()
