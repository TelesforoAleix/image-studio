import React, { useState, useEffect } from "react";
import { api } from "./api";

const empty = { verdict: null, asset_ratings: [], note: "", updated_at: null };

export function Feedback({ generation, output, act, busy, saved }) {
  const feedback = generation.feedback?.[output] || empty;
  const [draft, setDraft] = useState(null);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  const references = [
    ...new Map(generation.references.map((r) => [r.asset_id, r])).values(),
  ];
  const save = (value, detail = false) =>
    act(async () => {
      setSaving(true);
      try {
        const next = await api(
          `/generations/${generation.id}/outputs/${output}/feedback`,
          "PATCH",
          value,
        );
        saved(next);
        if (detail) setDraft(null);
        else if (draft) setDraft((old) => ({ ...old, verdict: next.verdict }));
        setNotice("Feedback saved.");
      } finally {
        setSaving(false);
      }
    });
  return (
    <div className="output-feedback">
      <div
        className="actions verdicts"
        aria-label={`Verdict for output ${output + 1}`}
      >
        {[
          ["good", "Good"],
          ["not_good", "Not good"],
        ].map(([value, label]) => (
          <button
            type="button"
            key={value}
            disabled={busy || saving}
            aria-pressed={feedback.verdict === value}
            onClick={() =>
              save({ verdict: feedback.verdict === value ? null : value })
            }
          >
            {label}
          </button>
        ))}
      </div>
      <button
        type="button"
        aria-expanded={!!draft}
        disabled={saving}
        onClick={() => {
          setDraft(draft ? null : { ...feedback });
          setNotice("");
        }}
      >
        {draft ? "Cancel feedback" : "Provide feedback"}
      </button>
      {draft && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            save(
              {
                verdict: draft.verdict,
                asset_ratings: draft.asset_ratings,
                note: draft.note,
              },
              true,
            );
          }}
        >
          <fieldset disabled={busy || saving}>
            <legend>Output {output + 1} feedback</legend>
            <label>
              Verdict
              <select
                value={draft.verdict || ""}
                onChange={(e) =>
                  setDraft({ ...draft, verdict: e.target.value || null })
                }
              >
                <option value="">Unrated</option>
                <option value="good">Good</option>
                <option value="not_good">Not good</option>
              </select>
            </label>
            {references.map((ref) => (
              <label key={ref.asset_id}>
                {ref.asset_name} · {ref.role}
                <select
                  value={
                    draft.asset_ratings.find((r) => r.asset_id === ref.asset_id)
                      ?.rating || ""
                  }
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      asset_ratings: [
                        ...draft.asset_ratings.filter(
                          (r) => r.asset_id !== ref.asset_id,
                        ),
                        ...(e.target.value
                          ? [{ asset_id: ref.asset_id, rating: e.target.value }]
                          : []),
                      ],
                    })
                  }
                >
                  <option value="">Unrated</option>
                  <option value="kept">Kept</option>
                  <option value="partly">Partly</option>
                  <option value="lost">Lost</option>
                </select>
              </label>
            ))}
            <label>
              Note (optional)
              <textarea
                rows={3}
                value={draft.note}
                onChange={(e) => setDraft({ ...draft, note: e.target.value })}
              />
            </label>
            <button type="submit">Save feedback</button>
          </fieldset>
        </form>
      )}
      {feedback.updated_at && (
        <small>Changed {new Date(feedback.updated_at).toLocaleString()}</small>
      )}
      <span role="status">{notice}</span>
    </div>
  );
}

export function OutputPage({ id, output, act, busy }) {
  const [generation, setGeneration] = useState(null);
  const [final, setFinal] = useState(null);
  useEffect(() => {
    act(async () => {
      const row = await api(`/generations/${id}`);
      if (!row.outputs[output]) throw new Error("Output not found");
      setGeneration(row);
      if (row.variant_id)
        setFinal(await api(`/variants/${row.variant_id}/final`));
    }, false);
  }, [id, output]);
  if (!generation) return <p>Loading output…</p>;
  return (
    <section className="large-output">
      <h2>
        {generation.model_info.display_name} · Output {output + 1}
      </h2>
      <a
        href={
          generation.variant_id
            ? `#frame/${generation.variant_id}`
            : `#asset/${generation.asset_id}`
        }
      >
        Back to {generation.variant_id ? "frame" : "asset"}
      </a>
      <img
        src={`/api/files/${generation.outputs[output]}`}
        alt={`Output ${output + 1}`}
      />
      <Feedback
        {...{ generation, output, act, busy }}
        saved={(feedback) =>
          setGeneration({
            ...generation,
            feedback: generation.feedback.map((f, i) =>
              i === output ? feedback : f,
            ),
          })
        }
      />
      {generation.variant_id && generation.state === "done" && (
        <button
          disabled={busy}
          onClick={() =>
            act(async () =>
              setFinal(
                await api(`/variants/${generation.variant_id}/final`, "PUT", {
                  generation_id: generation.id,
                  output,
                }),
              ),
            )
          }
        >
          {final?.generation_id === generation.id && final.output === output
            ? "Final"
            : "Mark final"}
        </button>
      )}
    </section>
  );
}
