/* Bound review-note validation shared by the offline page and browser tests. */
globalThis.PCBReviewNotes = (() => {
  const bindings = [
    "run",
    "checkpoint_sha256",
    "manifest_sha256",
    "prediction_sha256",
    "matching_code_sha256",
  ];
  const assessments = [
    "unreviewed",
    "looks_consistent",
    "needs_expert_review",
    "unclear",
  ];
  const thresholds = [0.05, 0.25, 0.5];
  const key = (n) =>
    `${n.image}#${n.subject_kind}#${n.subject_kind === "annotation" ? n.annotation_index : n.prediction_index}`;
  const canonical = (v) => {
    if (Array.isArray(v)) return "[" + v.map(canonical).join(",") + "]";
    if (v && typeof v === "object")
      return (
        "{" +
        Object.keys(v)
          .sort()
          .map((k) => JSON.stringify(k) + ":" + canonical(v[k]))
          .join(",") +
        "}"
      );
    return JSON.stringify(v);
  };
  const same = (a, b) => canonical(a) === canonical(b);
  function object(value, allowed, required = allowed) {
    if (
      !value ||
      typeof value !== "object" ||
      Array.isArray(value) ||
      Object.keys(value).some((k) => !allowed.includes(k)) ||
      required.some((k) => !Object.hasOwn(value, k))
    )
      throw new Error("Unexpected or missing note fields.");
  }
  function time(v) {
    if (
      typeof v !== "string" ||
      !/(Z|[+-]\d\d:\d\d)$/.test(v) ||
      !Number.isFinite(Date.parse(v))
    )
      throw new Error("Note timestamps must include a valid timezone.");
  }
  function validate(doc, data) {
    object(doc, [
      "schema_version",
      "purpose",
      ...bindings,
      "exported_at",
      "notes",
    ]);
    if (
      doc.schema_version !== "1.1" ||
      doc.purpose !== "Review notes only; no dataset changes"
    )
      throw new Error("Only review-note schema 1.1 is supported.");
    if (bindings.some((k) => doc[k] !== data[k]))
      throw new Error(
        "Notes belong to another run, checkpoint, dataset, predictions, or matcher.",
      );
    time(doc.exported_at);
    if (!Array.isArray(doc.notes) || doc.notes.length > 5000)
      throw new Error("Invalid note count.");
    const boards = new Map(data.boards.map((b) => [b.image, b]));
    const seen = new Set();
    for (const note of doc.notes) {
      const kind = note?.subject_kind;
      const common = [
        "image",
        "source_sha256",
        "group",
        "subject_kind",
        "assessment",
        "note",
        "score_threshold",
        "updated_at",
      ];
      const extra =
        kind === "annotation"
          ? ["annotation_index", "annotation"]
          : kind === "prediction"
            ? ["prediction_index", "prediction", "overlap_context"]
            : [];
      if (!extra.length) throw new Error("Unknown note subject.");
      object(note, [...common, ...extra]);
      if (
        typeof note.note !== "string" ||
        note.note.length > 4000 ||
        !assessments.includes(note.assessment) ||
        !thresholds.includes(note.score_threshold)
      )
        throw new Error("Invalid assessment, text, or threshold.");
      time(note.updated_at);
      const board = boards.get(note.image);
      if (
        !board ||
        note.source_sha256 !== board.source_sha256 ||
        note.group !== board.group
      )
        throw new Error("Note image, hash, or group differs from this review.");
      const index =
        kind === "annotation" ? note.annotation_index : note.prediction_index;
      const rows =
        kind === "annotation" ? board.annotations : board.predictions;
      if (
        !Number.isInteger(index) ||
        index < 0 ||
        index >= rows.length ||
        !same(note[kind], rows[index])
      )
        throw new Error(
          "Note subject differs from the original annotation or prediction.",
        );
      if (kind === "prediction") {
        const match = board.profiles[
          String(note.score_threshold)
        ].prediction_matches.find((m) => m.prediction_index === index);
        if (
          !match ||
          match.outcome === "matched" ||
          !same(match, note.overlap_context)
        )
          throw new Error(
            "Note overlap context differs from the recorded threshold.",
          );
      }
      if (seen.has(key(note)))
        throw new Error("Duplicate note subject in export.");
      seen.add(key(note));
    }
    return doc.notes;
  }
  function merge(existing, incoming) {
    const result = new Map(existing);
    for (const note of incoming) {
      const old = result.get(key(note));
      if (old && !same(old, note))
        throw new Error(
          "Conflicting note for the same subject. Keep separate exports for adjudication.",
        );
      result.set(key(note), note);
    }
    return result;
  }
  return { validate, merge, key };
})();
