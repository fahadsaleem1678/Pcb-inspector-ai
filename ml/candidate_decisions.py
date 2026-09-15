"""Record candidate reviews in immutable local ledgers without approving training."""

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

from ml.candidate_audit import digest
from ml.candidate_manifest import stable_id

FIELDS = {
    "pair": {
        "alignment": {"confirmed", "rejected", "needs_reference"},
        "normal_clean": {"confirmed", "rejected", "needs_reference"},
        "annotation_completeness": {"confirmed", "rejected", "needs_reference"},
    },
    "near": {"relationship": {"related", "unrelated", "needs_reference"}},
    "box": {"correction": {"accept", "reject", "needs_reference"}},
    "class": {"definition": {"retain_source", "needs_reference"}},
    "source": {"assessment": {"reviewed", "needs_reference"}},
}


def content_hash(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def read_json(path, limit=20_000_000):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    with Path(path).open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("JSON exceeds size limit")
    return json.loads(
        raw,
        object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
    )


def case_catalog(packet):
    if packet.get("schema_version") != "1.0" or packet.get("status") != "unreviewed_candidate":
        raise ValueError("Unsupported candidate packet")
    if (
        packet.get("ready_for_training") is not False
        or packet.get("production_eligible") is not False
    ):
        raise ValueError("Candidate packet cannot approve training or production")
    catalog = {}

    def add(identity, kind, subject):
        if identity in catalog:
            raise ValueError("Duplicate case identity")
        catalog[identity] = {"kind": kind, "subject": subject}

    for key, kind in (
        ("pair_cases", "pair"),
        ("near_duplicate_cases", "near"),
        ("border_corrections", "box"),
    ):
        for case in packet["review"][key]:
            add(case["case_id"], kind, case)
    for category in packet["review"]["class_definitions"]:
        add(
            stable_id("class", [packet["source"], category["source_category_id"]]),
            "class",
            category,
        )
    for topic in ("rights_and_provenance", "source_grouping_and_split_review"):
        add(stable_id("source", [packet["source"], topic]), "source", {"topic": topic})
    return catalog


def load_packet(packet_path, summary_path):
    summary = read_json(summary_path)
    if digest(packet_path) != summary["packet_sha256"]:
        raise ValueError("Packet hash differs from saved summary")
    packet = read_json(packet_path)
    if packet["binding"] != summary["binding"] or packet["source"] != summary["source"]:
        raise ValueError("Packet binding differs from summary")
    return packet, case_catalog(packet), summary["packet_sha256"]


def template(catalog, packet_hash):
    return {
        "schema_version": "1.0",
        "packet_sha256": packet_hash,
        "reviewer": None,
        "reviewed_at": None,
        "decisions": [
            {
                "case_id": identity,
                "answers": {field: None for field in FIELDS[case["kind"]]},
                "rationale": None,
            }
            for identity, case in sorted(catalog.items())
        ],
    }


def require_text(value, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError("Nonblank bounded review text required")


def reviewed_time(value):
    require_text(value, 80)
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Review time requires timezone")
    return result


def validate_batch(batch, catalog, packet_hash):
    if set(batch) != {"schema_version", "packet_sha256", "reviewer", "reviewed_at", "decisions"}:
        raise ValueError("Unexpected decision batch fields")
    if batch["schema_version"] != "1.0" or batch["packet_sha256"] != packet_hash:
        raise ValueError("Decision packet binding mismatch")
    require_text(batch["reviewer"], 200)
    reviewed_time(batch["reviewed_at"])
    decisions = batch["decisions"]
    if not isinstance(decisions, list) or not 1 <= len(decisions) <= len(catalog):
        raise ValueError("A nonempty bounded decision list is required")
    seen = set()
    for decision in decisions:
        if set(decision) != {"case_id", "answers", "rationale"}:
            raise ValueError("Unexpected decision fields")
        identity = decision["case_id"]
        if identity not in catalog or identity in seen:
            raise ValueError("Unknown or repeated case")
        seen.add(identity)
        require_text(decision["rationale"], 4000)
        fields = FIELDS[catalog[identity]["kind"]]
        if not isinstance(decision["answers"], dict) or set(decision["answers"]) != set(fields):
            raise ValueError("Wrong answer fields for case kind")
        for key, choices in fields.items():
            if (
                not isinstance(decision["answers"][key], str)
                or decision["answers"][key] not in choices
            ):
                raise ValueError("Invalid or blank review answer")


def review_state(batches, catalog, packet_hash):
    current, seen_batches = {}, set()
    for batch in batches:
        validate_batch(batch, catalog, packet_hash)
        batch_hash = content_hash(batch)
        if batch_hash in seen_batches:
            raise ValueError("Duplicate batch in ledger")
        seen_batches.add(batch_hash)
        for decision in batch["decisions"]:
            key = (decision["case_id"], batch["reviewer"])
            previous = current.get(key)
            if previous and reviewed_time(batch["reviewed_at"]) <= reviewed_time(
                previous["reviewed_at"]
            ):
                raise ValueError("Updated reviewer decisions require a later timestamp")
            current[key] = {
                "reviewer": batch["reviewer"],
                "reviewed_at": batch["reviewed_at"],
                "answers": decision["answers"],
                "rationale": decision["rationale"],
            }
    states = []
    for identity in sorted(catalog):
        observations = [value for (case, _), value in sorted(current.items()) if case == identity]
        choices = {content_hash(value["answers"]) for value in observations}
        needs_reference = any(
            "needs_reference" in value["answers"].values() for value in observations
        )
        status = (
            "unreviewed"
            if not observations
            else "conflicting"
            if len(choices) > 1
            else "needs_reference"
            if needs_reference
            else "recorded"
        )
        states.append({"case_id": identity, "status": status, "current_reviews": observations})
    return states


def validate_ledger(previous, catalog, packet_hash):
    expected = {
        "schema_version",
        "packet_sha256",
        "revision",
        "parent_sha256",
        "batches",
        "states",
        "ready_for_training",
        "production_eligible",
        "content_sha256",
    }
    if set(previous) != expected:
        raise ValueError("Unexpected ledger fields")
    body = {k: v for k, v in previous.items() if k != "content_sha256"}
    if content_hash(body) != previous["content_sha256"]:
        raise ValueError("Ledger content hash mismatch")
    if (
        previous["schema_version"] != "1.0"
        or previous["packet_sha256"] != packet_hash
        or previous["ready_for_training"] is not False
        or previous["production_eligible"] is not False
    ):
        raise ValueError("Ledger binding or eligibility mismatch")
    batches = previous["batches"]
    if previous["revision"] != len(batches):
        raise ValueError("Ledger revision mismatch")
    if review_state(batches, catalog, packet_hash) != previous["states"]:
        raise ValueError("Ledger state does not reproduce history")
    return previous["states"]


def import_batch(batch, catalog, packet_hash, previous=None, parent_hash=None):
    batches = []
    if previous is not None and (
        not isinstance(parent_hash, str)
        or len(parent_hash) != 64
        or any(c not in "0123456789abcdef" for c in parent_hash)
    ):
        raise ValueError("Previous ledger file hash required")
    if previous is None and parent_hash is not None:
        raise ValueError("Initial ledger cannot have a parent")
    if previous is not None:
        validate_ledger(previous, catalog, packet_hash)
        batches = previous["batches"]
    validate_batch(batch, catalog, packet_hash)
    if any(content_hash(old) == content_hash(batch) for old in batches):
        return previous, False
    combined = [*batches, batch]
    ledger = {
        "schema_version": "1.0",
        "packet_sha256": packet_hash,
        "revision": len(combined),
        "parent_sha256": parent_hash,
        "batches": combined,
        "states": review_state(combined, catalog, packet_hash),
        "ready_for_training": False,
        "production_eligible": False,
    }
    ledger["content_sha256"] = content_hash(ledger)
    return ledger, True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("template", "import"))
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--decisions", type=Path)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    _, catalog, packet_hash = load_packet(args.packet, args.summary)
    if args.output.exists():
        raise ValueError("Output exists; choose a new revision directory")
    if args.action == "template":
        if args.decisions or args.previous:
            raise ValueError("Template does not accept decisions or previous ledger")
        filename, result = "decisions-template.json", template(catalog, packet_hash)
    else:
        if not args.decisions:
            raise ValueError("Import requires --decisions")
        result, changed = import_batch(
            read_json(args.decisions, 5_000_000),
            catalog,
            packet_hash,
            read_json(args.previous) if args.previous else None,
            digest(args.previous) if args.previous else None,
        )
        if not changed:
            print("Identical batch already recorded; no revision created")
            return
        filename = "ledger.json"
    args.output.mkdir(parents=True)
    (args.output / filename).write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps({"output": str(args.output / filename), "ready_for_training": False}))


if __name__ == "__main__":
    main()
