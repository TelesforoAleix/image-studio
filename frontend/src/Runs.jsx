import React, { useEffect, useState } from "react";
import { api } from "./api";
import { ModelCost } from "./ModelCost";

function Badges({ info }) {
  return (
    <>
      {info.paid && <span className="badge">Paid</span>}{" "}
      {info.placeholder && <span className="badge">Placeholder</span>}{" "}
      <ModelCost info={info} />
    </>
  );
}

export function RunPicker({ models, choices, setChoices, references, busy }) {
  return (
    <fieldset disabled={busy}>
      <legend>Compare one to three models</legend>
      {choices
        .filter((c) => !models.some((m) => m.model_name === c.model))
        .map((c) => (
          <p className="error" key={c.model}>
            {c.model} is no longer available.{" "}
            <button
              type="button"
              onClick={() =>
                setChoices(choices.filter((x) => x.model !== c.model))
              }
            >
              Remove model
            </button>
          </p>
        ))}
      {models.map((m) => {
        const choice = choices.find((c) => c.model === m.model_name);
        const info = m.model_info;
        return (
          <div className="model-option" key={m.model_name}>
            <label>
              <span>
                <input
                  type="checkbox"
                  checked={!!choice}
                  disabled={!choice && choices.length >= 3}
                  onChange={(e) =>
                    setChoices(
                      e.target.checked
                        ? [...choices, { model: m.model_name, count: 1 }]
                        : choices.filter((c) => c.model !== m.model_name),
                    )
                  }
                />{" "}
                {info.display_name}
              </span>
            </label>
            <Badges info={info} />
            <p>
              Accepts {info.max_references} references ·{" "}
              {info.seconds_per_image == null
                ? "Time unknown"
                : `About ${info.seconds_per_image} seconds per image`}
            </p>
            {references > info.max_references && (
              <p className="limit-warning">
                {m.model_name}: selected {references} references; accepts at
                most {info.max_references}. Adjust your selection.
              </p>
            )}
            {choice && (
              <label>
                Outputs for {info.display_name}
                <select
                  value={choice.count}
                  onChange={(e) =>
                    setChoices(
                      choices.map((c) =>
                        c.model === choice.model
                          ? { ...c, count: Number(e.target.value) }
                          : c,
                      ),
                    )
                  }
                >
                  {[1, 2, 3, 4].map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>
        );
      })}
    </fieldset>
  );
}

function References({ references }) {
  return (
    <div className="reference-toggles">
      {references.map((r, i) => (
        <figure key={i}>
          <img
            src={`/api/files/${r.hash}`}
            alt={`Reference ${i + 1}: ${r.asset_name}`}
          />
          <figcaption>
            {i + 1}. {r.asset_name} · {r.role}
            <br />
            {r.description}
          </figcaption>
        </figure>
      ))}
    </div>
  );
}

export function PinnedReferences({ draft, setDraft, current }) {
  const contains = (r) =>
    current.some((c) => c.hash === r.hash && c.asset_id === r.asset_id);
  return (
    <div className="panel">
      <h3>Reused draft</h3>
      <p>
        The prompt, models and reference files are pinned to this draft. Changes
        to the current pack do not replace them.
      </p>
      <div className="reference-toggles">
        {draft.map((r, i) => (
          <figure key={i}>
            <img
              src={`/api/files/${r.hash}`}
              alt={`Reference ${i + 1}: ${r.asset_name}`}
            />
            <figcaption>
              {i + 1}. {r.asset_name} · {r.role}
            </figcaption>
            {!contains(r) && (
              <span className="badge">No longer in current pack</span>
            )}
            <button
              type="button"
              onClick={() => setDraft(draft.filter((_, j) => i !== j))}
            >
              Remove reference {i + 1}
            </button>
          </figure>
        ))}
      </div>
      <h3>Add from the current pack</h3>
      <div className="reference-toggles">
        {current
          .filter(
            (r) =>
              !draft.some(
                (d) => d.hash === r.hash && d.asset_id === r.asset_id,
              ),
          )
          .map((r, i) => (
            <figure key={i}>
              <img src={`/api/files/${r.hash}`} alt={r.asset_name} />
              <figcaption>
                {r.asset_name} · {r.role}
              </figcaption>
              <button type="button" onClick={() => setDraft([...draft, r])}>
                Add reference
              </button>
            </figure>
          ))}
      </div>
    </div>
  );
}

export function Runs({ variantId, act, busy, revision, reuse }) {
  const [runs, setRuns] = useState([]);
  const [final, setFinal] = useState(null);
  useEffect(() => {
    let active = true;
    let timer;
    async function load() {
      await act(async () => {
        const [next, picked] = await Promise.all([
          api(`/variants/${variantId}/runs`),
          api(`/variants/${variantId}/final`),
        ]);
        if (active) {
          setRuns(next);
          setFinal(picked);
        }
      }, false);
      if (active) timer = setTimeout(load, 3000);
    }
    load();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [variantId, revision]);
  const choose = (g, output) =>
    act(async () =>
      setFinal(
        await api(`/variants/${variantId}/final`, "PUT", {
          generation_id: g.id,
          output,
        }),
      ),
    );
  return (
    <>
      {final && (
        <div className="panel final-image">
          <h3>Final image</h3>
          <a href={`/api/files/${final.hash}`} target="_blank" rel="noreferrer">
            <img src={`/api/files/${final.hash}`} alt="Selected final image" />
          </a>
          <button
            disabled={busy}
            onClick={() =>
              act(async () =>
                setFinal(await api(`/variants/${variantId}/final`, "DELETE")),
              )
            }
          >
            Clear final
          </button>
        </div>
      )}
      {runs.map((run) => {
        const originals = run.generations.filter((g) => !g.retry_of);
        return (
          <article className="panel" key={run.run_id}>
            <div className="actions">
              <h3>Run · {new Date(run.created_at).toLocaleString()}</h3>
              <button disabled={busy} onClick={() => reuse(run)}>
                Reuse settings
              </button>
            </div>
            <details>
              <summary>Run snapshot</summary>
              <p>{run.edited ? "Edited prompt" : "Assembled prompt"}</p>
              <pre>{run.prompt}</pre>
              {originals.map((g) => (
                <details key={g.id}>
                  <summary>
                    {g.model_info.display_name} · {g.count} outputs
                  </summary>
                  <pre>{JSON.stringify(g.model_info, null, 2)}</pre>
                </details>
              ))}
              <References references={run.references} />
            </details>
            <div
              className="run-columns"
              style={{ "--columns": originals.length }}
            >
              {originals.map((original) => (
                <div className="model-column" key={original.id}>
                  <h3>{original.model_info.display_name}</h3>
                  <Badges info={original.model_info} />
                  {run.generations
                    .filter((g) => g.model === original.model)
                    .map((g) => (
                      <div className="attempt" key={g.id}>
                        <p>
                          {g.retry_of
                            ? `Retry of generation ${g.retry_of} · `
                            : ""}
                          {g.state} · {g.outputs.length}/{g.count}
                        </p>
                        {g.error && <p className="error">{g.error}</p>}
                        {g.state === "failed" && (
                          <button
                            disabled={busy}
                            onClick={() =>
                              act(async () => {
                                const retry = await api(
                                  `/generations/${g.id}/retry`,
                                  "POST",
                                );
                                setRuns((old) =>
                                  old.map((r) =>
                                    r.run_id === run.run_id
                                      ? {
                                          ...r,
                                          generations: [
                                            ...r.generations,
                                            retry,
                                          ],
                                        }
                                      : r,
                                  ),
                                );
                              })
                            }
                          >
                            Retry
                          </button>
                        )}
                        {g.outputs.map((hash, output) => (
                          <figure key={`${g.id}-${output}`}>
                            <a
                              href={`/api/files/${hash}`}
                              target="_blank"
                              rel="noreferrer"
                            >
                              <img
                                src={`/api/files/${hash}`}
                                alt={`${g.model_info.display_name}, output ${output + 1}`}
                              />
                            </a>
                            {g.state === "done" && (
                              <button
                                disabled={busy}
                                onClick={() => choose(g, output)}
                              >
                                {final?.generation_id === g.id &&
                                final.output === output
                                  ? "Final"
                                  : "Mark final"}
                              </button>
                            )}
                          </figure>
                        ))}
                      </div>
                    ))}
                </div>
              ))}
            </div>
          </article>
        );
      })}
      {!runs.length && <p>No runs yet.</p>}
    </>
  );
}
