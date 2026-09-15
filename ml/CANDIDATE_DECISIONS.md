# Versioned candidate reviewer decisions

The candidate decision importer records actual reviewer observations against an immutable
candidate packet. It preserves history and disagreements. It does not change source images,
annotations, groups or splits, and it does not approve training or production.

## Prepared templates

- [Meiwei template](runs/meiwei-decisions-template-001/decisions-template.json): 1,015 cases.
- [DsPCBSD+ template](runs/dspcbsd-decisions-template-001/decisions-template.json): 835 cases.

Templates contain null reviewer identity, timestamp, answers and rationales. No expert
observations have been fabricated or imported. Make a working copy; retain only the cases
actually reviewed in that submission. Partial batches are supported, empty batches and
blank answers are rejected. Match case_id to the original packet to inspect its subject.

Use the actual reviewer's identifier and an ISO timestamp with timezone, for example the
format YYYY-MM-DDTHH:MM:SS+05:00. Reviewer names are self-reported, not authenticated expert
credentials. Give specific reference evidence in each rationale (up to 4,000 characters).

| Case | Required answer keys | Permitted values |
| --- | --- | --- |
| Pair | alignment, normal_clean, annotation_completeness | confirmed / rejected / needs_reference, independently per field |
| Similarity | relationship | related / unrelated / needs_reference |
| Border correction | correction | accept / reject / needs_reference |
| Source class | definition | retain_source / needs_reference |
| Source provenance or grouping | assessment | reviewed / needs_reference |

A source assessment of reviewed records an observation; it is not a release approval.
Source-class review preserves the source category and cannot silently map it into the
current six-class contract. A correction acceptance refers only to the exact proposed box
in the hash-bound packet; custom replacement coordinates are not accepted in this format.

## Generate and import

Use the committed summary to verify the local packet hash and upstream binding. From the
repository root, choosing fresh output directories:

```powershell
.venv\Scripts\python.exe -m ml.candidate_decisions template --packet ml/runs/dspcbsd-candidate-review-001/candidate-review.json --summary ml/evidence/dspcbsd-candidate-review-001.json --output ml/runs/dspcbsd-decisions-template-new
.venv\Scripts\python.exe -m ml.candidate_decisions import --packet ml/runs/dspcbsd-candidate-review-001/candidate-review.json --summary ml/evidence/dspcbsd-candidate-review-001.json --decisions path/to/actual-reviewed-decisions.json --output ml/runs/dspcbsd-decisions-001
```

For later imports add `--previous ml/runs/dspcbsd-decisions-001/ledger.json` and choose a
new output directory. Keep every revision. The new ledger retains all batches and links
the exact prior file SHA256, with a canonical content checksum and reconstructed states.
Previously recorded exact batches are no-ops and create no revision directory. Existing
output directories cannot be overwritten. Validation failures create no output directory.

Different reviewers' answers are retained independently; differing answers mark a case
conflicting. A reviewer's later observation supersedes that reviewer's current view only,
while preserving the earlier batch. Updates to the same case by the same reviewer require
a strictly later timestamp. needs_reference remains unresolved. recorded means an
observation exists without a current disagreement; it does not mean approved or correct.

## Integrity and limits

The importer rejects packet/summary mismatch, unknown or repeated cases, extra fields,
wrong answer fields or values, missing rationale, timestamps without a timezone, changed
ledger content, and stored states that do not reproduce the retained history. JSON input
rejects duplicate keys and nonfinite values, with bounded reads (5 MB decision submissions;
20 MB packets/ledgers). The current revision embeds history; the importer verifies that
history and links the prior file but does not traverse older files on disk. Preserve the
revision chain for independent audit. Checksums provide content identity, not signatures.

The [candidate derivation command](CANDIDATE_DERIVATION.md) now derives versioned groups
and annotations from uncontested reviews while preserving source evidence and unresolved
cases. No actual reviews have been imported for these datasets. Release
and independent-split approval remain separate. Production camera/clean-board evaluation
and the still-undecided acceptable defective-board escape rate remain outstanding.

Validation: 207-test ML suite passed; two additional CLI checks passed afterward (22
importer tests total). Lint and formatting passed. [Template evidence](evidence/candidate-decision-templates-001.json)
records source packet and generated blank-template hashes.
