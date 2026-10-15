import { ActionGroup, ActionButton, ActionForm, ActionSelect } from "./Actions";
import React, { useEffect, useState } from "react";
import { api } from "./api";
import { Runs, PinnedReferences } from "./Runs";
import { ModelRequests } from "./ModelRequests";
import { Storyboard } from "./CompositionControls";
import { CompositionSetup } from "./CompositionSetup";

export function CompositionPage({ id, frameId, tab = "setup", projects, act }) {
  const [comp, setComp] = useState(null);
  const [assets, setAssets] = useState([]);
  const [assetId, setAssetId] = useState("");
  const [role, setRole] = useState("");
  const [direction, setDirection] = useState("");
  const [compName, setCompName] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [queuedRun, setQueuedRun] = useState(null);
  const [scene, setScene] = useState("");
  const [instructions, setInstructions] = useState("");
  const [preview, setPreview] = useState(null);
  const [previewError, setPreviewError] = useState("");
  const [draftContent, setDraftContent] = useState("");
  const [format, setFormat] = useState("1:1");
  const [rendered, setRendered] = useState(null);
  const [models, setModels] = useState([]);
  const [choices, setChoices] = useState([]);
  const [draft, setDraft] = useState(null);
  const [revision, setRevision] = useState(0);
  const [frameName, setFrameName] = useState("");
  const variant = comp?.variants.find((v) => v.id === Number(frameId));
  const navigate = (nextTab, nextFrame = variant?.id) => {
    window.location.hash = `composition/${id}/frame/${nextFrame}/${nextTab}`;
  };
  useEffect(() => {
    act(async () => {
      const c = await api(`/compositions/${id}`);
      const frame = c.variants.find((v) => v.id === Number(frameId));
      if (!frame) {
        window.location.replace(
          `#composition/${id}/frame/${c.variants[0].id}/setup`,
        );
        return;
      }
      setComp(c);
      setScene(c.scene);
      setDirection(c.direction);
      setCompName(c.name);
      setInstructions(frame?.instructions ?? "");
      setFrameName(frame?.name ?? "");
      setAssets(await api("/assets"));
      setModels(await api("/models"));
    }, false);
  }, [id, frameId]);
  useEffect(() => {
    if (!variant) return;
    setInstructions(variant.instructions);
    setFrameName(variant.name);
    setDraft(null);
    setDraftContent("");
    setQueuedRun(null);
  }, [variant?.id]);
  useEffect(() => {
    if (!variant) return;
    let active = true;
    setPreview(null);
    const timer = setTimeout(
      () =>
        (async () => {
          try {
            const result = await api(
              `/variants/${variant.id}/preview`,
              "POST",
              {
                direction,
                scene,
                instructions,
              },
            );
            if (active) {
              setPreview(result);
              setPreviewError("");
            }
          } catch (e) {
            if (active) setPreviewError(e.message);
          }
        })(),
      200,
    );
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [comp, direction, scene, instructions]);
  if (!comp || !variant) return <p>Loading composition…</p>;
  const saveSelection = (s) =>
    act(async () =>
      setComp(
        await api(`/compositions/${comp.id}/assets/${s.asset_id}`, "PUT", {
          role: s.role,
          deselected_images: s.deselected_images,
          selected_originals: s.selected_originals,
        }),
      ),
    );
  async function saveText() {
    await api(`/variants/${variant.id}`, "PATCH", {
      name: frameName,
      instructions,
    });
    setComp(
      await api(`/compositions/${comp.id}`, "PATCH", {
        name: compName,
        direction,
        scene,
      }),
    );
  }
  const references = draft ?? preview?.references ?? [];
  const invalidModels =
    !choices.length ||
    choices.some((c) => {
      const info = models.find((m) => m.model_name === c.model)?.model_info;
      return !info || references.length > info.max_references;
    });
  const available = assets.filter(
    (a) => a.type !== "style" && !comp.assets.some((s) => s.asset_id === a.id),
  );
  return (
    <section>
      <div className="library-header">
        <h2>{comp.name}</h2>
        <a href="#compositions">Compositions</a>
      </div>
      <ActionGroup className="composition-header">
        <label>
          Kind
          <ActionSelect
            value={comp.kind}
            onChange={(e) =>
              act(async () =>
                setComp(
                  await api(`/compositions/${comp.id}`, "PATCH", {
                    kind: e.target.value,
                  }),
                ),
              )
            }
          >
            <option value="single" disabled={comp.variants.length > 1}>
              Single image
            </option>
            <option value="storyboard">Storyboard</option>
          </ActionSelect>
        </label>
        <label>
          Project
          <ActionSelect
            value={comp.project_id ?? ""}
            onChange={(e) =>
              act(async () =>
                setComp(
                  await api(`/compositions/${comp.id}`, "PATCH", {
                    project_id: e.target.value ? Number(e.target.value) : null,
                  }),
                ),
              )
            }
          >
            <option value="">No project</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </ActionSelect>
        </label>
      </ActionGroup>
      <div className="actions">
        <a
          className="button-link"
          href={`/api/compositions/${comp.id}/sequence.zip`}
        >
          Export images
        </a>
        <a
          className="button-link"
          href={`/api/compositions/${comp.id}/export.zip`}
        >
          Export package
        </a>
        <ActionButton
          className={tab === "history" ? "primary" : "secondary"}
          onClick={() =>
            act(async () => {
              const copy = await api(
                `/compositions/${comp.id}/duplicate`,
                "POST",
              );
              window.location.hash = `composition/${copy.id}`;
            })
          }
        >
          Duplicate
        </ActionButton>
        <ActionButton
          className="destructive"
          onClick={() => setConfirming(true)}
        >
          Delete…
        </ActionButton>
      </div>
      <p className="export-note">
        {comp.variants.some((v) => !v.final)
          ? `Export images skips frames without finals: ${comp.variants
              .filter((v) => !v.final)
              .map((v) => v.name)
              .join(", ")}`
          : "Export images includes every frame final."}
      </p>
      {confirming && (
        <div className="panel delete-confirm">
          <p>
            Hide “{comp.name}”? Its frames, runs, finals and files remain
            stored.
          </p>
          <ActionButton
            className="destructive"
            onClick={() =>
              act(async () => {
                await api(`/compositions/${comp.id}`, "DELETE");
                window.location.hash = "compositions";
              })
            }
          >
            Yes, delete composition
          </ActionButton>
          <ActionButton className="plain" onClick={() => setConfirming(false)}>
            Cancel
          </ActionButton>
        </div>
      )}
      {comp.kind === "storyboard" && (
        <Storyboard
          {...{ comp, setComp, act }}
          selected={variant.id}
          tab={tab}
          navigate={navigate}
        />
      )}
      {previewError && (
        <p className="error" role="alert">
          {previewError}
        </p>
      )}
      <nav className="composition-tabs" aria-label="Composition tabs">
        {["setup", "generate", "history"].map((t) => (
          <a
            key={t}
            href={`#composition/${id}/frame/${variant.id}/${t}`}
            aria-current={tab === t ? "page" : undefined}
          >
            {t[0].toUpperCase() + t.slice(1)}
          </a>
        ))}
      </nav>
      {tab === "setup" && (
        <CompositionSetup
          {...{
            comp,
            compName,
            setCompName,
            direction,
            setDirection,
            scene,
            setScene,
            frameName,
            setFrameName,
            instructions,
            setInstructions,
            act,
            saveText,
            available,
            assetId,
            setAssetId,
            role,
            setRole,
            setComp,
            saveSelection,
            variant,
          }}
        />
      )}
      {tab === "generate" && (
        <>
          {draft !== null && (
            <>
              <PinnedReferences
                draft={draft}
                setDraft={setDraft}
                current={preview?.references ?? []}
              />
              <ActionButton
                type="button"
                onClick={() => {
                  setDraft(null);
                  setDraftContent("");
                }}
              >
                Back to the current pack
              </ActionButton>
            </>
          )}
          <div className="panel">
            <ActionForm
              success="Run queued."
              onSubmit={(e) => {
                e.preventDefault();
                act(async () => {
                  await saveText();
                  const run = await api(
                    `/variants/${variant.id}/runs`,
                    "POST",
                    {
                      models: choices,
                      ...(draft !== null ? { references: draft } : {}),
                      format,
                      ...(draft !== null ? { content: draftContent } : {}),
                    },
                  );
                  setQueuedRun(run.run_id);
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
                content={draft !== null ? draftContent : preview?.prompt}
                references={references}
                onPreview={setRendered}
              />
              <ActionButton
                className="primary"
                disabled={
                  invalidModels || (draft === null && !preview) || !rendered
                }
              >
                Generate
              </ActionButton>
            </ActionForm>
          </div>
          {queuedRun && (
            <Runs
              variantId={variant.id}
              {...{ act, revision }}
              runId={queuedRun}
              reuse={() => {}}
            />
          )}
        </>
      )}
      {tab === "history" && (
        <>
          <h3>{frameName} results</h3>
          <Runs
            variantId={variant.id}
            {...{ act, revision }}
            refresh={() =>
              act(
                async () => setComp(await api(`/compositions/${comp.id}`)),
                false,
              )
            }
            reuse={(run) => {
              setDraft(run.references.map((r) => ({ ...r })));
              setChoices(
                run.generations
                  .filter((g) => !g.retry_of)
                  .map((g) => ({
                    model: g.model,
                    count: g.count,
                    prompt: g.prompt,
                    ...(g.settings ? { settings: g.settings } : {}),
                  })),
              );
              setDraftContent(run.generations[0].assembled_prompt);
              setFormat(run.generations[0].settings?.format || "1:1");
              navigate("generate");
            }}
          />
        </>
      )}
    </section>
  );
}
