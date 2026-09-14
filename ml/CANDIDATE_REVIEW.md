# Candidate source grouping and review packets

The candidate packet generator prepares review material from hash-bound source audits.
It does not create a training release, accept expert decisions, or assign new dataset splits.
The existing six-class dataset and model holdout remain unchanged.

## Generated local packets

| Source | Images | Provisional groups | Similarity cases | Other cases |
| --- | --- | --- | --- | --- |
| MeiweiPCB | 1,938 | 966 | 43 | 969 normal/defect pair reviews |
| DsPCBSD+ | 10,259 | 10,259 | 453 | 371 border correction reviews |

Open the local JSON packets:

- [Meiwei packet](runs/meiwei-candidate-review-001/candidate-review.json)
- [DsPCBSD+ packet](runs/dspcbsd-candidate-review-001/candidate-review.json)

Full packets are ignored local artifacts. Committed [Meiwei summary](evidence/meiwei-candidate-review-001.json)
and [DsPCBSD+ summary](evidence/dspcbsd-candidate-review-001.json) bind their exact bytes, input
audit, input inventory and generator SHA256. These hashes establish reproducibility and
content identity, not authenticated source provenance or reviewer credentials.

## Grouping rules

Image identities include source, condition, original split and filename. Every image has
one provisional group. Filename-paired Meiwei defect/reference images are joined, and
identical decoded pixels are joined across the whole source, including conditions.
Connections are transitive: a duplicate reference can link both of its paired defect views.
Group IDs are content-derived membership identifiers, not claimed physical-board IDs.
Input order does not change the resulting groups or packet.

Two Meiwei groups cross the inherited source splits. Their proposed split stays null.
No source split is silently preferred and no evaluation image is reassigned to training.
DsPCBSD+ has no exact image duplicate links; 10,259 singleton groups do not establish
10,259 independent physical boards. Related-capture/source-layout review is still required.

Similarity cases are reconstructed exhaustively from each condition's inventory using the
same dHash method as the audit, so all 496 cases are retained despite audit display limits.
Similarity alone never merges groups. This scan covers cross-source-split pairs within each
condition at original orientation; it is not an exhaustive proof of capture independence.
Each case records whether exact/pair evidence has already linked the images.

## Review fields and next work

Make a separate working copy before recording actual reviewer observations. Each packet
contains member filenames, archive member paths, dimensions and hashes to locate originals
in the source archives recorded by the bound audit. No candidate images are copied into Git.

- Pair cases: verify alignment, whether the normal patch is clean, annotation completeness,
  and any source-group evidence. Author naming alone does not fill these decisions.
- Similarity cases: record whether the images are related captures, with reference evidence.
  Repetitive conductor patterns can create false matches.
- Border cases: compare original and proposed COCO xywh coordinates. Record an actual
  acceptance decision and rationale; source annotations are unchanged by packet creation.
- Class definitions: all nine DsPCBSD+ source categories are retained. Current-project
  mappings and definition reviews remain null. Do not treat hole breakout as missing pad.
- Source-level review: record actual reviewer/time, provenance/rights and grouping evidence.

Use the [versioned decision importer](CANDIDATE_DECISIONS.md) to record real reviewer
observations against the packet hash. It preserves history and disagreements without
changing source data or approving a release. The importer has separate strict decision
submission templates; editing the packet itself invalidates its committed summary hash.
A subsequent derived-candidate and split proposal must keep every accepted related group
together and reserve independent evaluation data before a new training release is frozen.
Do not edit ready_for_training or production_eligible to bypass those steps.

## Reproduce

From the repository root, use fresh output directories:

```powershell
.venv\Scripts\python.exe -m ml.candidate_manifest --audit ml/evidence/meiwei-source-audit-001.json --inventory ml/runs/meiwei-audit-004/inventory.json --output ml/runs/meiwei-candidate-review-new
.venv\Scripts\python.exe -m ml.candidate_manifest --audit ml/evidence/dspcbsd-source-audit-001.json --inventory ml/runs/dspcbsd-audit-004/inventory.json --output ml/runs/dspcbsd-candidate-review-new
```

The tool rejects changed inventory bytes, unsupported sources/schema, duplicate image
identities, incomplete/reused pairs, mismatched image/annotation or similarity counts,
and correction proposals whose original annotation differs from the inventory.
An existing output directory is rejected. Original files are read only.

Validation: 187 ML tests passed, including 11 manifest regression cases; Ruff lint and
format checks passed. Both complete source packets were generated and hash-verified.
