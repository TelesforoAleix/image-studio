import {
  ActionButton,
  ActionForm,
  ActionSelect,
  ActionTextarea,
} from "./Actions";
import React, {
  useState,
  useEffect,
  forwardRef,
  useImperativeHandle,
  useRef,
} from "react";
import { api } from "./api";

const empty = { verdict: null, asset_ratings: [], note: "", updated_at: null };

export const Feedback = forwardRef(function Feedback(
  { generation, output, act, saved, primary = false, shortcuts = false },
  ref,
) {
  const root = useRef(null);
  const feedback = generation.feedback?.[output] || empty;
  const [draft, setDraft] = useState(null);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 4000);
    return () => clearTimeout(timer);
  }, [notice]);
  const references = [
    ...new Map(
      generation.references
        .filter((r) => r.asset_id != null)
        .map((r) => [r.asset_id, r]),
    ).values(),
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
        if (detail) {
          setDraft(null);
          setNotice("Feedback saved.");
        } else if (draft)
          setDraft((old) => ({ ...old, verdict: next.verdict }));
      } finally {
        setSaving(false);
      }
    });
  useImperativeHandle(ref, () => ({
    verdict: (value) =>
      root.current?.querySelector(`[data-verdict="${value}"]`)?.click(),
    open: () => {
      if (!draft) root.current?.querySelector("[data-detail]")?.click();
    },
    cancel: () => {
      if (!draft) return false;
      setDraft(null);
      root.current?.querySelector("[data-detail]")?.focus();
      return true;
    },
  }));
  useEffect(() => {
    if (shortcuts && draft) root.current?.querySelector("select")?.focus();
  }, [!!draft]);
  return (
    <div ref={root} className="output-feedback">
      <div
        className="actions verdicts"
        aria-label={`Verdict for output ${output + 1}`}
      >
        {[
          ["good", "Good"],
          ["not_good", "Not good"],
        ].map(([value, label]) => (
          <ActionButton
            data-verdict={value}
            success="Feedback saved."
            type="button"
            key={value}
            disabled={saving}
            aria-pressed={feedback.verdict === value}
            onClick={() =>
              save({ verdict: feedback.verdict === value ? null : value })
            }
          >
            {label}
            {shortcuts && (
              <>
                {" "}
                <kbd>{value === "good" ? "G" : "N"}</kbd>
              </>
            )}
          </ActionButton>
        ))}
      </div>
      <ActionButton
        data-detail
        type="button"
        className={primary && !draft ? "primary" : "plain"}
        aria-expanded={!!draft}
        disabled={saving}
        onClick={() => {
          setDraft(draft ? null : { ...feedback });
        }}
      >
        {draft ? "Cancel feedback" : "Provide feedback"}
        {shortcuts && (
          <>
            {" "}
            <kbd>{draft ? "Esc" : "Enter"}</kbd>
          </>
        )}
      </ActionButton>
      {draft && (
        <ActionForm
          success="Feedback saved."
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
          <fieldset disabled={saving}>
            <legend>Output {output + 1} feedback</legend>
            <label>
              Verdict
              <ActionSelect
                value={draft.verdict || ""}
                onChange={(e) =>
                  setDraft({ ...draft, verdict: e.target.value || null })
                }
              >
                <option value="">Unrated</option>
                <option value="good">Good</option>
                <option value="not_good">Not good</option>
              </ActionSelect>
            </label>
            {references.map((ref) => (
              <label key={ref.asset_id}>
                {ref.asset_name} · {ref.role}
                <ActionSelect
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
                </ActionSelect>
              </label>
            ))}
            <label>
              Note (optional)
              <ActionTextarea
                rows={3}
                value={draft.note}
                onChange={(e) => setDraft({ ...draft, note: e.target.value })}
              />
            </label>
            <ActionButton
              className={primary ? "primary" : "secondary"}
              type="submit"
            >
              Save feedback
            </ActionButton>
          </fieldset>
        </ActionForm>
      )}
      {notice && <span role="status">{notice}</span>}
      {feedback.updated_at && (
        <small>Changed {new Date(feedback.updated_at).toLocaleString()}</small>
      )}
    </div>
  );
});
