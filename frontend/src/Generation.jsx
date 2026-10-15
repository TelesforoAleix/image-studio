import { useViewerSource, ComparePick, outputHref } from "./OutputViewer";
import { usePolling } from "./usePolling";
import { hasActive, GenerationProgress } from "./Progress";
import { ActionButton, ActionForm, ActionSelect } from "./Actions";
import React, { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { ModelRequests } from "./ModelRequests";
import { Feedback } from "./Feedback";
import { ModelCost } from "./ModelCost";

export function ModelPicker({
  models,
  model,
  setModel,
  count,
  setCount,
  references,
}) {
  const info = models.find((m) => m.model_name === model)?.model_info;
  return (
    <>
      <label>
        Model
        <ActionSelect
          required
          value={model}
          onChange={(e) => setModel(e.target.value)}
        >
          <option value="">Choose a model</option>
          {models.map((m) => (
            <option key={m.model_name} value={m.model_name}>
              {m.model_info.display_name}
            </option>
          ))}
        </ActionSelect>
      </label>
      <div className="model-list">
        {models.map((m) => (
          <p key={m.model_name}>
            {m.model_info.display_name}{" "}
            {m.model_info.paid && <span className="badge">Paid</span>}{" "}
            {m.model_info.placeholder && (
              <span className="badge">Placeholder</span>
            )}{" "}
            <ModelCost info={m.model_info} /> · accepts{" "}
            {m.model_info.max_references} references ·{" "}
            {m.model_info.seconds_per_image == null
              ? "Time unknown"
              : `About ${m.model_info.seconds_per_image} seconds per image`}
          </p>
        ))}
      </div>
      <p>
        {references} references selected
        {info &&
          references > info.max_references &&
          `; this model accepts at most ${info.max_references}. Adjust your selection.`}
      </p>
      <label>
        Outputs
        <ActionSelect
          value={count}
          onChange={(e) => setCount(Number(e.target.value))}
        >
          {[1, 2, 3, 4].map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </ActionSelect>
      </label>
    </>
  );
}

export function History({ path, act, revision, refresh }) {
  const [items, setItems] = useState([]);
  const previous = useRef("");
  const refreshRef = useRef(refresh);
  refreshRef.current = refresh;
  const pollError = usePolling(
    async (active) => {
      const next = await api(path);
      if (!active()) return;
      setItems(next);
      const signature = next.map((g) => g.outputs.join(",")).join(";");
      if (signature !== previous.current && refreshRef.current)
        await refreshRef.current();
      previous.current = signature;
    },
    hasActive(items),
    path,
    revision,
  );
  const saveFeedback = (id, output, feedback) =>
    setItems((old) =>
      old.map((g) =>
        g.id === id
          ? {
              ...g,
              feedback: g.outputs.map((_, i) =>
                i === output ? feedback : g.feedback?.[i],
              ),
            }
          : g,
      ),
    );
  const groups = new Map();
  items.forEach((g) => {
    const key = g.run_id || g.id;
    if (!groups.has(key)) groups.set(key, { generations: [] });
    groups.get(key).generations.push(g);
  });
  useViewerSource({ runs: [...groups.values()], saveFeedback }, [items]);
  return (
    <div className="image-grid">
      {pollError && (
        <p className="error" role="alert">
          {pollError}
        </p>
      )}
      {items.map((g) => (
        <article className="image-card" key={g.id}>
          <div className="image-info">
            <strong>
              <GenerationProgress generation={g} />
            </strong>
            <span>{g.model_info.display_name}</span>
            <ModelCost info={g.model_info} />
            {g.placeholder && <span className="badge">Placeholder trial</span>}
            <small>{new Date(g.created_at).toLocaleString()}</small>
            {g.error && <p>{g.error}</p>}
            {g.outputs.map((hash, i) => (
              <div key={`${g.id}-${i}`}>
                <a data-output href={outputHref(g.id, i)}>
                  <img src={`/api/files/${hash}`} alt={`Output ${i + 1}`} />
                </a>
                <ComparePick generation={g} output={i} />
                <Feedback
                  generation={g}
                  output={i}
                  {...{ act }}
                  saved={(feedback) =>
                    setItems((old) =>
                      old.map((row) =>
                        row.id === g.id
                          ? {
                              ...row,
                              feedback: row.feedback.map((f, index) =>
                                index === i ? feedback : f,
                              ),
                            }
                          : row,
                      ),
                    )
                  }
                />
              </div>
            ))}
            <details>
              <summary>Input snapshot</summary>
              <p>
                {g.edited
                  ? "Prompt edited for this generation"
                  : "Assembled prompt"}
              </p>
              <p>Shared content</p>
              <pre>{g.assembled_prompt}</pre>
              <p>Rendered prompt ({g.prompt_family || "legacy"})</p>
              <pre>{g.rendered_prompt || g.assembled_prompt}</pre>
              <p>Prompt as sent</p>
              <pre>{g.prompt}</pre>
              <p>
                Estimated cost:{" "}
                {g.estimated_cost == null
                  ? "Unavailable for past run"
                  : `$${g.estimated_cost}`}
              </p>
              <pre>
                {JSON.stringify(
                  { settings: g.settings, request_fields: g.request_fields },
                  null,
                  2,
                )}
              </pre>
              {g.references.map((r, i) => (
                <figure key={i}>
                  <img
                    src={`/api/files/${r.hash}`}
                    alt={`Reference ${i + 1}: ${r.asset_name}`}
                  />
                  <figcaption>
                    {i + 1}. {r.role}: {r.asset_name}
                    <br />
                    {r.description}
                  </figcaption>
                </figure>
              ))}
              {!g.references.length && <p>No reference images</p>}
            </details>
          </div>
        </article>
      ))}
    </div>
  );
}

export function ReferenceGeneration({ id, act, refresh, inputRevision }) {
  const [models, setModels] = useState([]);
  const [choices, setChoices] = useState([]);
  const [format, setFormat] = useState("1:1");
  const [rendered, setRendered] = useState(null);
  const [preview, setPreview] = useState(null);
  const [revision, setRevision] = useState(0);
  const [loadError, setLoadError] = useState("");
  useEffect(() => {
    let active = true;
    Promise.all([api("/models"), api(`/assets/${id}/reference-preview`)])
      .then(([nextModels, nextPreview]) => {
        if (active) {
          setModels(nextModels);
          setPreview(nextPreview);
          setLoadError("");
        }
      })
      .catch((e) => {
        if (active) setLoadError(e.message);
      });
    return () => {
      active = false;
    };
  }, [id, revision, inputRevision]);
  return (
    <div className="panel">
      <h3>Generate reference views</h3>
      {loadError && (
        <p className="error" role="alert">
          {loadError}
        </p>
      )}
      <p>
        Uses this asset’s uploaded photos. Approve or reject each candidate
        above.
      </p>
      <ActionForm
        success="Reference views queued."
        onSubmit={(e) => {
          e.preventDefault();
          act(async () => {
            await api(`/assets/${id}/generations`, "POST", choices[0]);
            setRevision((n) => n + 1);
          });
        }}
      >
        <ModelRequests
          {...{
            models,
            choices,
            setChoices,
            format,
            setFormat,
            revision,
          }}
          content={preview?.prompt}
          references={preview?.references || []}
          onPreview={setRendered}
          limit={1}
        />
        <ActionButton disabled={!rendered || choices.length !== 1}>
          Generate reference views
        </ActionButton>
      </ActionForm>
      <History
        path={`/assets/${id}/generations`}
        {...{ act, revision, refresh }}
      />
    </div>
  );
}
