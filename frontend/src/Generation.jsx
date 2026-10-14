import React, { useEffect, useRef, useState } from "react";
import { api } from "./api";
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
        <select
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
        </select>
      </label>
      <div className="model-list">
        {models.map((m) => (
          <p key={m.model_name}>
            {m.model_info.display_name}{" "}
            {m.model_info.paid && <span className="badge">Paid</span>}{" "}
            {m.model_info.placeholder && (
              <span className="badge">Placeholder</span>
            )}{" "}
            <ModelCost info={m.model_info} /> · accepts {m.model_info.max_references} references ·{" "}
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
        <select
          value={count}
          onChange={(e) => setCount(Number(e.target.value))}
        >
          {[1, 2, 3, 4].map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      </label>
    </>
  );
}

export function History({ path, act, revision, refresh }) {
  const [items, setItems] = useState([]);
  const previous = useRef("");
  const refreshRef = useRef(refresh);
  refreshRef.current = refresh;
  useEffect(() => {
    let active = true;
    let timer;
    async function load() {
      await act(async () => {
        const next = await api(path);
        if (!active) return;
        setItems(next);
        const signature = next.map((g) => g.outputs.join(",")).join(";");
        if (signature !== previous.current && refreshRef.current)
          await refreshRef.current();
        previous.current = signature;
      }, false);
      if (active) timer = setTimeout(load, 3000);
    }
    load();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [path, revision]);
  return (
    <div className="image-grid">
      {items.map((g) => (
        <article className="image-card" key={g.id}>
          <div className="image-info">
            <strong>
              {g.state} · {g.outputs.length}/{g.count}
            </strong>
            <span>{g.model_info.display_name}</span>
            <ModelCost info={g.model_info} />
            {g.placeholder && <span className="badge">Placeholder trial</span>}
            <small>{new Date(g.created_at).toLocaleString()}</small>
            {g.error && <p>{g.error}</p>}
            {g.outputs.map((hash, i) => (
              <a
                key={`${hash}-${i}`}
                href={`/api/files/${hash}`}
                target="_blank"
                rel="noreferrer"
              >
                <img src={`/api/files/${hash}`} alt={`Output ${i + 1}`} />
              </a>
            ))}
            <details>
              <summary>Input snapshot</summary>
              <p>
                {g.edited
                  ? "Prompt edited for this generation"
                  : "Assembled prompt"}
              </p>
              <pre>{g.prompt}</pre>
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

export function ReferenceGeneration({ id, act, busy, refresh, inputRevision }) {
  const [models, setModels] = useState([]);
  const [model, setModel] = useState("");
  const [count, setCount] = useState(1);
  const [preview, setPreview] = useState(null);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    act(async () => {
      setModels(await api("/models"));
      setPreview(await api(`/assets/${id}/reference-preview`));
    }, false);
  }, [id, revision, inputRevision]);
  return (
    <div className="panel">
      <h3>Generate reference views</h3>
      <p>
        Uses this asset’s uploaded photos. Approve or reject each candidate
        above.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          act(async () => {
            await api(`/assets/${id}/generations`, "POST", { model, count });
            setRevision((n) => n + 1);
          });
        }}
      >
        <ModelPicker
          {...{ models, model, setModel, count, setCount }}
          references={preview?.references.length || 0}
        />
        {preview && (
          <details>
            <summary>Reference-view prompt</summary>
            <pre>{preview.prompt}</pre>
          </details>
        )}
        <button
          disabled={
            busy ||
            !model ||
            !preview ||
            preview.references.length >
              (models.find((m) => m.model_name === model)?.model_info
                .max_references ?? 0)
          }
        >
          Generate reference views
        </button>
      </form>
      <History
        path={`/assets/${id}/generations`}
        {...{ act, revision, refresh }}
      />
    </div>
  );
}
