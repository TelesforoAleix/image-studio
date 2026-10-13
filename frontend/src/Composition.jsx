import React, { useEffect, useState } from "react";
import { api } from "./api";
import { ProjectForm } from "./ProjectForm";
import { Runs, RunPicker, PinnedReferences } from "./Runs";

export function ProjectPage({ id, act, changed, busy }) {
  const [project, setProject] = useState(null);
  const [compositions, setCompositions] = useState([]);
  const [name, setName] = useState("");
  useEffect(() => {
    act(async () => {
      setProject(await api(`/projects/${id}`));
      setCompositions(await api(`/projects/${id}/compositions`));
    }, false);
  }, [id]);
  if (!project) return <p>Loading project…</p>;
  return (
    <section>
      <div className="library-header">
        <h2>{project.name}</h2>
        <a href="#projects">Projects</a>
      </div>
      <ProjectForm {...{ project, act, changed, busy }} />
      <div className="panel">
        <h3>Compositions</h3>
        {compositions.map((c) => (
          <p key={c.id}>
            <a href={`#composition/${c.id}`}>{c.name}</a>
          </p>
        ))}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            act(async () => {
              const c = await api(`/projects/${id}/compositions`, "POST", {
                name,
              });
              window.location.hash = `composition/${c.id}`;
            });
          }}
        >
          <label>
            New composition name
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <button disabled={busy}>Create composition</button>
        </form>
      </div>
    </section>
  );
}

function Selection({ selection, save, remove, busy }) {
  const [role, setRole] = useState(selection.role);
  return (
    <div className="panel">
      <h3>{selection.asset.name}</h3>
      <label>
        Role
        <input
          value={role}
          onChange={(e) => setRole(e.target.value)}
          onBlur={() => {
            if (role !== selection.role) save({ ...selection, role });
          }}
        />
      </label>
      {selection.asset.deleted_at && (
        <p>This asset was deleted. Remove it to generate.</p>
      )}
      <div className="reference-toggles">
        {selection.asset.images
          .filter((i) => i.approved && !i.rejected)
          .map((i) => (
            <label key={i.id}>
              <img src={`/api/files/${i.hash}`} alt={selection.asset.name} />
              <span>
                <input
                  type="checkbox"
                  disabled={busy}
                  checked={!selection.deselected_images.includes(i.id)}
                  onChange={(e) =>
                    save({
                      ...selection,
                      deselected_images: e.target.checked
                        ? selection.deselected_images.filter((x) => x !== i.id)
                        : [...selection.deselected_images, i.id],
                    })
                  }
                />
                Use reference {i.id}
              </span>
            </label>
          ))}
      </div>
      <button type="button" disabled={busy} onClick={remove}>
        Remove asset
      </button>
    </div>
  );
}

export function CompositionPage({ id, frameId, act, busy }) {
  const [comp, setComp] = useState(null);
  const [assets, setAssets] = useState([]);
  const [assetId, setAssetId] = useState("");
  const [role, setRole] = useState("");
  const [scene, setScene] = useState("");
  const [instructions, setInstructions] = useState("");
  const [preview, setPreview] = useState(null);
  const [editing, setEditing] = useState(false);
  const [edited, setEdited] = useState("");
  const [models, setModels] = useState([]);
  const [choices, setChoices] = useState([]);
  const [draft, setDraft] = useState(null);
  const [revision, setRevision] = useState(0);
  const [frameName, setFrameName] = useState("");
  const variant = comp?.variants.find((v) => v.id === Number(frameId));
  useEffect(() => {
    act(async () => {
      const frame = frameId ? await api(`/variants/${frameId}`) : null;
      if (frame?.deleted_at) throw new Error("This frame has been deleted.");
      const c = await api(`/compositions/${frame?.composition_id ?? id}`);
      setComp(c);
      setScene(c.scene);
      setInstructions(frame?.instructions ?? "");
      setFrameName(frame?.name ?? "");
      setAssets(await api(`/assets?project_id=${c.project_id}`));
      if (frameId) setModels(await api("/models"));
    }, false);
  }, [id, frameId]);
  useEffect(() => {
    if (!variant) return;
    let active = true;
    setPreview(null);
    const timer = setTimeout(
      () =>
        act(async () => {
          const result = await api(`/variants/${variant.id}/preview`, "POST", {
            scene,
            instructions,
          });
          if (active) setPreview(result);
        }, false),
      200,
    );
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [comp, scene, instructions]);
  if (!comp) return <p>Loading composition…</p>;
  const saveSelection = (s) =>
    act(async () =>
      setComp(
        await api(`/compositions/${comp.id}/assets/${s.asset_id}`, "PUT", {
          role: s.role,
          deselected_images: s.deselected_images,
        }),
      ),
    );
  async function saveText() {
    if (frameId) {
      await api(`/variants/${variant.id}`, "PATCH", {
        name: frameName,
        instructions,
      });
    } else {
      setComp(await api(`/compositions/${comp.id}`, "PATCH", { scene }));
    }
  }
  const references = draft ?? preview?.references ?? [];
  const invalidModels =
    !choices.length ||
    choices.some((c) => {
      const info = models.find((m) => m.model_name === c.model)?.model_info;
      return !info || references.length > info.max_references;
    });
  const available = assets.filter(
    (a) => !comp.assets.some((s) => s.asset_id === a.id),
  );
  return (
    <section>
      <div className="library-header">
        <h2>{frameId ? frameName : comp.name}</h2>
        {frameId ? (
          <a href={`#composition/${comp.id}`}>
            Back to storyboard and shared pack
          </a>
        ) : (
          <a href={`#project/${comp.project_id}`}>Back to project</a>
        )}
      </div>
      {!frameId && (
        <Storyboard comp={comp} setComp={setComp} act={act} busy={busy} />
      )}
      <form
        className="panel"
        onSubmit={(e) => {
          e.preventDefault();
          act(saveText);
        }}
      >
        {!frameId && (
          <label>
            Shared scene instructions
            <textarea
              rows="5"
              value={scene}
              onChange={(e) => setScene(e.target.value)}
            />
          </label>
        )}
        {frameId && (
          <>
            <p>
              Assets, roles and scene are shared by every frame. Edit them on
              the storyboard page.
            </p>
            <label>
              Frame name
              <input
                required
                value={frameName}
                onChange={(e) => setFrameName(e.target.value)}
              />
            </label>
            <label>
              Frame instructions
              <textarea
                rows="3"
                value={instructions}
                onChange={(e) => setInstructions(e.target.value)}
              />
            </label>
          </>
        )}
        <button disabled={busy}>Save instructions</button>
      </form>
      {!frameId && (
        <>
          <h3>Shared asset pack · all frames</h3>
          <form
            className="panel"
            onSubmit={(e) => {
              e.preventDefault();
              act(async () => {
                setComp(
                  await api(
                    `/compositions/${comp.id}/assets/${assetId}`,
                    "PUT",
                    {
                      role,
                    },
                  ),
                );
                setAssetId("");
                setRole("");
              });
            }}
          >
            <h3>Add an asset</h3>
            <label>
              Visible assets
              <select
                required
                value={assetId}
                onChange={(e) => setAssetId(e.target.value)}
              >
                <option value="">Choose an asset</option>
                {available.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Role
              <input
                required
                value={role}
                onChange={(e) => setRole(e.target.value)}
                placeholder="For example, the background"
              />
            </label>
            <button disabled={busy || !assetId}>Add asset</button>
          </form>
          {comp.assets.map((s) => (
            <Selection
              key={s.id}
              selection={s}
              save={saveSelection}
              busy={busy}
              remove={() =>
                act(async () =>
                  setComp(
                    await api(
                      `/compositions/${comp.id}/assets/${s.asset_id}`,
                      "DELETE",
                    ),
                  ),
                )
              }
            />
          ))}
        </>
      )}
      {frameId && (
        <>
          <div className="panel">
            <h3>References for this frame</h3>
            <p>Switch off selected pack images for this frame only.</p>
            <div className="reference-toggles">
              {comp.assets.flatMap((s) =>
                s.asset.images
                  .filter(
                    (i) =>
                      i.approved &&
                      !i.rejected &&
                      !s.deselected_images.includes(i.id),
                  )
                  .map((i) => (
                    <label key={i.id}>
                      <img src={`/api/files/${i.hash}`} alt={s.asset.name} />
                      <span>
                        <input
                          type="checkbox"
                          disabled={busy}
                          checked={!variant.deselected_images.includes(i.id)}
                          onChange={(e) =>
                            act(async () => {
                              const available = comp.assets.flatMap((s) =>
                                s.asset.images
                                  .filter(
                                    (i) =>
                                      i.approved &&
                                      !i.rejected &&
                                      !s.deselected_images.includes(i.id),
                                  )
                                  .map((i) => i.id),
                              );
                              const deselected =
                                variant.deselected_images.filter(
                                  (x) => available.includes(x) && x !== i.id,
                                );
                              if (!e.target.checked) deselected.push(i.id);
                              await api(`/variants/${variant.id}`, "PATCH", {
                                deselected_images: deselected,
                              });
                              setComp(await api(`/compositions/${comp.id}`));
                            })
                          }
                        />
                        Use {s.asset.name} reference {i.id}
                      </span>
                    </label>
                  )),
              )}
            </div>
          </div>
          {draft !== null && (
            <>
              <PinnedReferences
                draft={draft}
                setDraft={setDraft}
                current={preview?.references ?? []}
              />
              <button
                type="button"
                onClick={() => {
                  setDraft(null);
                  setEditing(false);
                  setEdited("");
                }}
              >
                Back to the current pack
              </button>
            </>
          )}
          <div className="panel">
            <h3 id="prompt-editor">Prompt to send</h3>
            {editing ? (
              <label>
                Edited prompt
                <textarea
                  rows="12"
                  value={edited}
                  onChange={(e) => setEdited(e.target.value)}
                />
              </label>
            ) : (
              <pre>{preview?.prompt || "Preparing preview…"}</pre>
            )}
            <div className="actions">
              <button
                type="button"
                disabled={!preview}
                onClick={() => {
                  if (!editing) setEdited(preview.prompt);
                  setEditing(true);
                }}
              >
                Edit
              </button>
              <button
                type="button"
                disabled={draft !== null}
                onClick={() => {
                  if (draft === null) {
                    setEditing(false);
                    setEdited("");
                  }
                }}
              >
                Reset
              </button>
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                act(async () => {
                  await saveText();
                  await api(`/variants/${variant.id}/runs`, "POST", {
                    models: choices,
                    ...(draft !== null ? { references: draft } : {}),
                    prompt: editing ? edited : preview.prompt,
                  });
                  setRevision((n) => n + 1);
                });
              }}
            >
              <RunPicker
                models={models}
                choices={choices}
                setChoices={setChoices}
                references={references.length}
                busy={busy}
              />
              <button
                disabled={
                  busy ||
                  invalidModels ||
                  (draft === null && !preview) ||
                  (editing && !edited.trim())
                }
              >
                Generate
              </button>
            </form>
          </div>
          <h3>{frameName} results</h3>
          <Runs
            variantId={variant.id}
            {...{ act, busy, revision }}
            reuse={(run) => {
              setDraft(run.references.map((r) => ({ ...r })));
              setChoices(
                run.generations
                  .filter((g) => !g.retry_of)
                  .map((g) => ({ model: g.model, count: g.count })),
              );
              setEdited(run.prompt);
              setEditing(true);
              document
                .getElementById("prompt-editor")
                ?.scrollIntoView({ behavior: "smooth" });
            }}
          />
        </>
      )}
    </section>
  );
}

function Storyboard({ comp, setComp, act, busy }) {
  const [confirming, setConfirming] = useState(null);
  const [manifest, setManifest] = useState(null);
  useEffect(() => {
    act(
      async () => setManifest(await api(`/compositions/${comp.id}/sequence`)),
      false,
    );
  }, [comp]);
  const move = (index, delta) =>
    act(async () => {
      const ids = comp.variants.map((v) => v.id);
      [ids[index], ids[index + delta]] = [ids[index + delta], ids[index]];
      setComp(
        await api(`/compositions/${comp.id}/frame-order`, "PUT", { ids }),
      );
    });
  return (
    <>
      <div className="panel">
        <h3>Storyboard</h3>
        <p>
          One shared asset pack, with instructions and a final image for each
          frame.
        </p>
        <button
          disabled={busy}
          onClick={() =>
            act(async () => {
              await api(`/compositions/${comp.id}/variants`, "POST", {});
              setComp(await api(`/compositions/${comp.id}`));
            })
          }
        >
          Add frame
        </button>
      </div>
      {comp.variants.map((v, index) => (
        <article className="panel storyboard-frame" key={v.id}>
          <h3>
            {index + 1}. {v.name}
          </h3>
          <p className="frame-instructions">
            {v.instructions || "No instructions yet."}
          </p>
          {v.final ? (
            <a
              href={`/api/files/${v.final.hash}`}
              target="_blank"
              rel="noreferrer"
            >
              <img
                src={`/api/files/${v.final.hash}`}
                alt={`${v.name} final image`}
              />
            </a>
          ) : (
            <p>No final yet</p>
          )}
          <div className="actions">
            <a href={`#frame/${v.id}`}>Work on {v.name}</a>
            <button
              disabled={busy || index === 0}
              onClick={() => move(index, -1)}
            >
              Move up
            </button>
            <button
              disabled={busy || index === comp.variants.length - 1}
              onClick={() => move(index, 1)}
            >
              Move down
            </button>
            <button
              className="danger"
              disabled={busy || comp.variants.length === 1}
              onClick={() => setConfirming(v.id)}
            >
              Delete frame…
            </button>
          </div>
          {confirming === v.id && (
            <div className="delete-confirm">
              <p>
                Hide “{v.name}” with its runs and final? All generations and
                files remain stored.
              </p>
              <button
                className="danger"
                disabled={busy}
                onClick={() =>
                  act(async () => {
                    await api(`/variants/${v.id}`, "DELETE");
                    setComp(await api(`/compositions/${comp.id}`));
                    setConfirming(null);
                  })
                }
              >
                Yes, delete frame
              </button>
              <button onClick={() => setConfirming(null)}>Cancel</button>
            </div>
          )}
        </article>
      ))}
      <div className="panel">
        <h3>Export sequence</h3>
        {manifest ? (
          <>
            <p>
              {manifest.skipped.length
                ? `Skipped (no final): ${manifest.skipped.map((v) => v.name).join(", ")}`
                : "Every frame has a final image."}
            </p>
            {manifest.entries.length ? (
              <a href={`/api/compositions/${comp.id}/sequence.zip`}>
                Export sequence · {manifest.entries.length} images
              </a>
            ) : (
              <p>Select a final image to export.</p>
            )}
          </>
        ) : (
          <p>Checking final images…</p>
        )}
      </div>
    </>
  );
}
