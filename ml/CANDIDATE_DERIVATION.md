# Derived candidate groups and annotations

The derivation command produces a new, unapproved candidate from a hash-bound inventory,
review packet and optional validated decision ledger. It never modifies the original
archives, inventories, review packets, ledgers or frozen training release.

## Rules for applying reviews

- Only recorded, uncontested answers can affect derived data. Unreviewed, conflicting and
  needs_reference cases remain explicit blockers. No reviewer identity is invented.
- An accepted border correction changes only the derived annotation at the bound image and
  index. The original category and coordinates must match. The proposed result must exactly
  reproduce the bounded border normalization (at most 0.02-pixel overshoot). The change log
  retains before/after coordinates and the source decision case ID.
- Accepted related-capture observations join existing groups transitively. Existing exact
  duplicate and filename-pair groups are never split. An unrelated decision that contradicts
  existing or newly accepted links becomes a blocker; it cannot break those links.
- Rejected normal/pair reviews and rejected border corrections remain blockers. Every source
  image and annotation remains in the candidate; the tool does not erase inconvenient defects
  or manufacture clean-negative labels. Remaining invalid boxes are listed separately.
- Source category IDs and names are preserved, including all nine DsPCBSD+ categories.
  No mapping into the existing six-class training contract is performed.

Every proposed split and physical-board identity remains null. Even if all case blockers
are resolved, explicit training release, source independence, expert completeness review
and independent-split approval are still required. ready_for_training and
production_eligible always remain false. A locally derived file is not a deployable model.

## Current complete-data previews

No real reviewer ledger has been supplied. These previews apply zero corrections and zero
new reviewed links, and demonstrate that absent reviews cannot approve changes:

| Source | Images / boxes preserved | Groups | Unreviewed cases | Invalid boxes remaining |
| --- | --- | --- | --- | --- |
| MeiweiPCB | 1,938 / 1,275 | 966 | 1,015 | 0 |
| DsPCBSD+ | 10,259 / 20,276 | 10,259 | 835 | 277 |

[Meiwei evidence](evidence/meiwei-derived-preview-001.json) and
[DsPCBSD+ evidence](evidence/dspcbsd-derived-preview-001.json) bind full local candidate
files, packet, inventory and derivation/decision code hashes. Their ledger hash is null.
Full output files live under ignored ml/runs/*-derived-preview-001 directories.
Two Meiwei groups still cross the inherited source splits. DsPCBSD+ singleton groups are
not evidence of independent physical boards. Neither source supplies verified clean whole
boards for production qualification.

## Commands

From the repository root, choosing fresh output directories:

```powershell
.venv\Scripts\python.exe -m ml.candidate_derive --packet ml/runs/dspcbsd-candidate-review-001/candidate-review.json --summary ml/evidence/dspcbsd-candidate-review-001.json --inventory ml/runs/dspcbsd-audit-004/inventory.json --output ml/runs/dspcbsd-derived-preview-new
```

To apply actual reviews, add `--ledger path/to/validated-review-revision/ledger.json`.
The importer and derivation share ledger validation: checksums, packet binding, revision
count and stored states must reproduce the full batch history. A changed inventory or
packet fails its saved hash. Hashes provide content identity, not reviewer authentication.
Existing output directories are rejected; use a new directory for each candidate revision.
Compare the candidate's applied_corrections, reviewed_group_links, case_blockers and
remaining_invalid_boxes before proceeding to a separately reviewed split/release proposal.

The next practical requirement is real expert review using the
[decision workflow](CANDIDATE_DECISIONS.md). A visual review interface can make those cases
easier to inspect; it cannot substitute for source provenance or actual expert decisions.

Validation: 221 ML tests passed, including 12 derivation cases for accepted/conflicting/
rejected/unresolved reviews, source preservation, group contradictions and input tampering.
Ruff lint and formatting checks passed.
