import { useViewerSource, ComparePick, outputHref } from "./OutputViewer";
import { usePolling } from "./usePolling";
import { hasActive, GenerationProgress } from "./Progress";
import { ActionButton, ActionInput, ActionSelect } from "./Actions";
import React, { useEffect, useState } from "react";
import { api } from "./api";
import { Feedback } from "./Feedback";
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

export function RunPicker({ models, choices, setChoices, references }) {
  return (
    <fieldset>
      <legend>Compare one to three models</legend>
      {choices
        .filter((c) => !models.some((m) => m.model_name === c.model))
        .map((c) => (
          <p className="error" key={c.model}>
            {c.model} is no longer available.{" "}
            <ActionButton
              className="plain"
              type="button"
              onClick={() =>
                setChoices(choices.filter((x) => x.model !== c.model))
              }
            >
              Remove model
            </ActionButton>
          </p>
        ))}
      {models.map((m) => {
        const choice = choices.find((c) => c.model === m.model_name);
        const info = m.model_info;
        return (
          <div className="model-option" key={m.model_name}>
            <label>
              <span>
                <ActionInput
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
                <ActionSelect
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
                </ActionSelect>
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
            <ActionButton
              type="button"
              onClick={() => setDraft(draft.filter((_, j) => i !== j))}
            >
              Remove reference {i + 1}
            </ActionButton>
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
              <ActionButton
                type="button"
                onClick={() => setDraft([...draft, r])}
              >
                Add reference
              </ActionButton>
            </figure>
          ))}
      </div>
    </div>
  );
}

export function Runs({
  variantId,
  act,
  revision,
  reuse,
  runId,
  refresh,
  workspace = false,
  queuedRun,
}) {
  const [runs, setRuns] = useState([]);
  const [selected, setSelected] = useState(null);
  useEffect(() => {
    if (queuedRun) {
      setRuns((old) => [
        queuedRun,
        ...old.filter((r) => r.run_id !== queuedRun.run_id),
      ]);
      setSelected(queuedRun.run_id);
    }
  }, [queuedRun]);
  const [final, setFinal] = useState(null);
  const pollError = usePolling(
    async (active) => {
      const [next, picked] = await Promise.all([
        api(`/variants/${variantId}/runs`),
        api(`/variants/${variantId}/final`),
      ]);
      if (active()) {
        setRuns(next);
        setFinal(picked);
      }
    },
    hasActive(runs.flatMap((r) => r.generations)),
    variantId,
    revision,
  );
  const choose = (g, output) =>
    act(async () => {
      setFinal(
        await api(`/variants/${variantId}/final`, "PUT", {
          generation_id: g.id,
          output,
        }),
      );
      if (refresh) await refresh();
    });
  const saveFeedback = (id, output, feedback) =>
    setRuns((old) =>
      old.map((run) => ({
        ...run,
        generations: run.generations.map((g) =>
          g.id === id
            ? {
                ...g,
                feedback: g.feedback.map((f, i) =>
                  i === output ? feedback : f,
                ),
              }
            : g,
        ),
      })),
    );
  useViewerSource({ runs, final, choose, saveFeedback }, [runs, final]);
  const tallies = {};
  runs.forEach((r) =>
    r.generations.forEach((g) => {
      const tally = (tallies[g.model] ||= {
        name: g.model_info.display_name,
        rated: 0,
        good: 0,
      });
      g.feedback.forEach((f) => {
        tally.rated += f.verdict !== null ? 1 : 0;
        tally.good += f.verdict === "good" ? 1 : 0;
      });
    }),
  );
  const finalGeneration = runs
    .flatMap((r) => r.generations)
    .find((g) => g.id === final?.generation_id);
  return (
    <>
      {pollError && (
        <p className="error" role="alert">
          {pollError}
        </p>
      )}
      {!runId && (
        <div className="actions feedback-tally" aria-label="Feedback per model">
          {Object.entries(tallies).map(([model, tally]) => (
            <small key={model}>
              {tally.name}: {tally.rated} rated · {tally.good} good
            </small>
          ))}
        </div>
      )}
      {!workspace && !runId && final && (
        <div className="panel final-image">
          <h3>Final image</h3>
          <a data-output href={outputHref(final.generation_id, final.output)}>
            <img src={`/api/files/${final.hash}`} alt="Selected final image" />
          </a>
          {finalGeneration && (
            <Feedback
              generation={finalGeneration}
              output={final.output}
              {...{ act }}
              saved={(f) => saveFeedback(finalGeneration.id, final.output, f)}
            />
          )}
          <ActionButton
            className="plain"
            onClick={() =>
              act(async () => {
                setFinal(await api(`/variants/${variantId}/final`, "DELETE"));
                if (refresh) await refresh();
              })
            }
          >
            Clear final
          </ActionButton>
        </div>
      )}
      {workspace && final && (
        <ActionButton
          className="plain"
          onClick={() =>
            act(async () => {
              setFinal(await api(`/variants/${variantId}/final`, "DELETE"));
              if (refresh) await refresh();
            })
          }
        >
          Clear final
        </ActionButton>
      )}
      {runs
        .filter((run) =>
          workspace
            ? run.run_id ===
              (runs.some((r) => r.run_id === selected)
                ? selected
                : runs[0]?.run_id)
            : !runId || run.run_id === runId,
        )
        .map((run) => {
          const originals = run.generations.filter((g) => !g.retry_of);
          return (
            <article className="panel" key={run.run_id}>
              <div className="actions">
                <h3>Run · {new Date(run.created_at).toLocaleString()}</h3>
                {!runId && (
                  <ActionButton onClick={() => reuse(run)}>
                    Reuse settings
                  </ActionButton>
                )}
              </div>
              <details>
                <summary>
                  {workspace ? "Technical details" : "Run snapshot"}
                </summary>
                <p>{run.edited ? "Edited prompt" : "Assembled prompt"}</p>
                <pre>{run.prompt}</pre>
                {originals.map((g) => (
                  <details key={g.id}>
                    <summary>
                      {g.model_info.display_name} · {g.count} outputs
                    </summary>
                    <p>Shared content</p>
                    <pre>{g.assembled_prompt}</pre>
                    <p>Rendered prompt ({g.prompt_family || "legacy"})</p>
                    <pre>{g.rendered_prompt || g.assembled_prompt}</pre>
                    <p>Prompt as sent{g.edited ? " (edited)" : ""}</p>
                    <pre>{g.prompt}</pre>
                    <p>
                      Estimated cost:{" "}
                      {g.estimated_cost == null
                        ? "Unavailable for past run"
                        : `$${g.estimated_cost}`}
                    </p>
                    <pre>
                      {JSON.stringify(
                        {
                          settings: g.settings,
                          request_fields: g.request_fields,
                          model_info: g.model_info,
                        },
                        null,
                        2,
                      )}
                    </pre>
                    <References references={g.references} />
                  </details>
                ))}
                <References references={run.references} />
                <pre>{JSON.stringify(run, null, 2)}</pre>
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
                            <GenerationProgress generation={g} />
                          </p>
                          {g.error && <p className="error">{g.error}</p>}
                          {g.state === "failed" && (
                            <ActionButton
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
                            </ActionButton>
                          )}
                          {g.outputs.map((hash, output) => (
                            <figure key={`${g.id}-${output}`}>
                              <a data-output href={outputHref(g.id, output)}>
                                <img
                                  src={`/api/files/${hash}`}
                                  alt={`${g.model_info.display_name}, output ${output + 1}`}
                                />
                              </a>
                              <ComparePick generation={g} output={output} />
                              <Feedback
                                generation={g}
                                {...{ output, act }}
                                saved={(f) => saveFeedback(g.id, output, f)}
                              />
                              {g.state === "done" && (
                                <ActionButton
                                  aria-pressed={
                                    final?.generation_id === g.id &&
                                    final.output === output
                                  }
                                  onClick={() => choose(g, output)}
                                >
                                  {final?.generation_id === g.id &&
                                  final.output === output
                                    ? "Final"
                                    : "Mark final"}
                                </ActionButton>
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
      {workspace && runs.length > 0 && (
        <div className="earlier-runs">
          <h3>Earlier runs</h3>
          <div className="run-strip" aria-label="Earlier runs">
            {runs.map((run) => (
              <button
                type="button"
                key={run.run_id}
                aria-pressed={
                  run.run_id ===
                  (runs.some((r) => r.run_id === selected)
                    ? selected
                    : runs[0]?.run_id)
                }
                onClick={() => setSelected(run.run_id)}
              >
                <span className="run-thumbnails">
                  {run.generations
                    .flatMap((g) => g.outputs)
                    .slice(0, 3)
                    .map((hash, i) => (
                      <img key={i} src={`/api/files/${hash}`} alt="" />
                    ))}
                </span>
                <time>{new Date(run.created_at).toLocaleString()}</time>
                <span>
                  {[
                    ...new Set(
                      run.generations.map((g) => g.model_info.display_name),
                    ),
                  ].join(", ")}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
      {!runs.length && (
        <div className="empty-library">
          <h3>Your next image starts here</h3>
          <p>
            Write a brief, choose a model and generate. Your runs will appear
            beside your instructions.
          </p>
        </div>
      )}
    </>
  );
}
