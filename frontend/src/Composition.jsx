import { ActionButton, ActionForm, ActionSelect } from "./Actions";
import React, { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { Runs } from "./Runs";
import { ModelRequests, formats } from "./ModelRequests";
import { Storyboard } from "./CompositionControls";
import { CompositionSetup } from "./CompositionSetup";
import { WorkspaceMenu } from "./WorkspaceMenu";
import { usePolling } from "./usePolling";
import { useAutosave } from "./useAutosave";

export function CompositionPage({ id, frameId, projects, act, onProject }) {
  const [comp, setComp] = useState(null);
  const [assets, setAssets] = useState([]);
  useEffect(() => onProject(comp?.project_id), [comp?.project_id, onProject]);
  const [models, setModels] = useState([]);
  useEffect(() => {
    let active = true;
    act(async () => {
      const [c, a, m] = await Promise.all([
        api(`/compositions/${id}`),
        api("/assets"),
        api("/models"),
      ]);
      if (!active) return;
      setComp(c);
      setAssets(a);
      setModels(m);
    }, false);
    return () => {
      active = false;
    };
  }, [id]);
  useEffect(() => {
    if (comp && !comp.variants.some((v) => v.id === Number(frameId)))
      window.location.replace(
        `#composition/${id}/frame/${comp.variants[0].id}`,
      );
  }, [comp, frameId, id]);
  const sequencePollError = usePolling(
    async (active) => {
      const next = await api(`/compositions/${id}`);
      if (active()) setComp(next);
    },
    comp?.sequences?.some((s) => ["running", "stopping"].includes(s.state)),
    id,
    0,
  );
  const variant = comp?.variants.find((v) => v.id === Number(frameId));
  if (!comp || !variant) return <p>Loading composition…</p>;
  return (
    <Workspace
      key={variant.id}
      {...{
        comp,
        setComp,
        assets,
        models,
        variant,
        projects,
        act,
        sequencePollError,
      }}
    />
  );
}

export function referenceWarnings(choices, models, references) {
  return choices.flatMap((c) => {
    const info = models.find((m) => m.model_name === c.model)?.model_info;
    if (!info) return [`${c.model}: no longer available.`];
    const warnings = [];
    if (references.length > info.max_references)
      warnings.push(
        `${info.display_name}: selected ${references.length} references; accepts at most ${info.max_references}.`,
      );
    for (const [slot, limit] of Object.entries(info.reference_slots || {})) {
      const count = references.filter((r) =>
        slot === "character" ? r.type === "person" : r.type !== "person",
      ).length;
      if (count > limit)
        warnings.push(
          `${info.display_name}: selected ${count} ${slot} references; accepts at most ${limit}.`,
        );
    }
    return warnings;
  });
}
const runSettings = (run, prompts = false) => ({
  choices: run.generations
    .filter((g) => !g.retry_of)
    .map((g) => ({
      model: g.model,
      count: g.count,
      ...(g.settings ? { settings: g.settings } : {}),
      ...(prompts ? { prompt: g.prompt } : {}),
    })),
  format: run.generations[0]?.settings?.format || "1:1",
});

function Workspace({
  comp,
  setComp,
  assets,
  models,
  variant,
  projects,
  act,
  sequencePollError,
}) {
  const autosave = useAutosave(comp, variant, setComp);
  const { brief, instructions } = autosave.value;
  const [preview, setPreview] = useState(null);
  const [previewError, setPreviewError] = useState("");
  const [choices, setChoices] = useState([]);
  const [format, setFormat] = useState("1:1");
  const [rendered, setRendered] = useState(null);
  const [revision, setRevision] = useState(0);
  const [queuedRun, setQueuedRun] = useState(null);
  const [draft, setDraft] = useState(null);
  const [draftContent, setDraftContent] = useState("");
  const [reusedAt, setReusedAt] = useState("");
  const remembered = useRef(null);
  const [initialized, setInitialized] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [moving, setMoving] = useState(false);
  const [toolbar, setToolbar] = useState({
    pending: false,
    error: "",
    notice: "",
  });
  useEffect(() => {
    if (!toolbar.notice) return;
    const timer = setTimeout(
      () => setToolbar((old) => ({ ...old, notice: "" })),
      4000,
    );
    return () => clearTimeout(timer);
  }, [toolbar.notice]);
  const toolbarAction = async (task) => {
    setToolbar({ pending: true, error: "", notice: "" });
    try {
      await task();
      setToolbar({ pending: false, error: "", notice: "Saved." });
    } catch (e) {
      setToolbar({ pending: false, error: e.message, notice: "" });
    }
  };
  const form = useRef(null);
  const bar = useRef(null);
  useEffect(() => {
    const resize = new ResizeObserver(() => {
      bar.current
        ?.closest(".composition-workspace")
        .style.setProperty(
          "--generate-bar-height",
          `${bar.current.getBoundingClientRect().height}px`,
        );
    });
    resize.observe(bar.current);
    return () => resize.disconnect();
  }, []);
  const navigate = async (next) => {
    await autosave.flush();
    window.location.hash = `composition/${comp.id}/frame/${next}`;
  };
  const refresh = async () => setComp(await api(`/compositions/${comp.id}`));
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const own = await api(`/variants/${variant.id}/runs`);
        let latest = own[0];
        if (!latest) {
          const others = await Promise.all(
            comp.variants
              .filter((v) => v.id !== variant.id)
              .map((v) => api(`/variants/${v.id}/runs`)),
          );
          latest = others
            .flat()
            .sort(
              (a, b) => Date.parse(b.created_at) - Date.parse(a.created_at),
            )[0];
        }
        if (active) {
          if (latest) {
            const settings = runSettings(latest);
            setChoices(settings.choices);
            setFormat(settings.format);
          }
          if (!latest && models.length) {
            const ratios = models.flatMap((m) => formats(m.model_info));
            setFormat(ratios.includes("1:1") ? "1:1" : ratios[0] || "1:1");
          }
          setInitialized(true);
        }
      } catch (e) {
        if (active) setPreviewError(e.message);
      }
    })();
    return () => {
      active = false;
    };
  }, [variant.id]);
  useEffect(() => {
    let active = true;
    const timer = setTimeout(async () => {
      try {
        const result = await api(`/variants/${variant.id}/preview`, "POST", {
          brief,
          instructions,
        });
        if (active) {
          setPreview(result);
          setPreviewError("");
        }
      } catch (e) {
        if (active) setPreviewError(e.message);
      }
    }, 200);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [comp, brief, instructions]);
  useEffect(() => {
    const key = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault();
        form.current?.requestSubmit();
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, []);
  const references = draft ?? preview?.references ?? [];
  const warnings = referenceWarnings(choices, models, references);
  const patch = (value) =>
    toolbarAction(async () => {
      await autosave.flush();
      setComp(await api(`/compositions/${comp.id}`, "PATCH", value));
    });
  const sequence = comp.sequences?.[0];
  const activeSequence =
    sequence && ["running", "stopping"].includes(sequence.state);
  const selectedIndex = comp.variants.findIndex((f) => f.id === variant.id);
  const failedFrame =
    sequence?.state === "failed"
      ? sequence.frames[sequence.current_frame]?.frame_id
      : null;
  const restIndex = failedFrame
    ? comp.variants.findIndex((f) => f.id === failedFrame)
    : selectedIndex;
  const perFrameCost = rendered?.reduce((sum, p) => sum + p.estimated_cost, 0);
  const startSequence = (mode) =>
    toolbarAction(async () => {
      await autosave.flush();
      await api(`/compositions/${comp.id}/frame-sequences`, "POST", {
        mode,
        frame_id: mode === "rest" ? failedFrame || variant.id : variant.id,
        models: choices,
        format,
      });
      await refresh();
      setRevision((n) => n + 1);
    });
  const canGenerate =
    initialized && choices.length && !warnings.length && preview && rendered;
  return (
    <section className="composition-workspace">
      <div className="workspace-toolbar">
        <div className="breadcrumb">
          <span>
            {projects.find((p) => p.id === comp.project_id)?.name ||
              "No project"}
          </span>{" "}
          › <strong>{autosave.value.name}</strong>
          {comp.kind === "storyboard" && (
            <> › {autosave.value.frameName}</>
          )}{" "}
          <span className="badge">
            {comp.kind === "single" ? "Single image" : "Storyboard"}
          </span>
        </div>
        <div className="actions">
          <WorkspaceMenu label="Share">
            <a
              role="menuitem"
              href={`/api/compositions/${comp.id}/sequence.zip`}
            >
              Export images
            </a>
            <a role="menuitem" href={`/api/compositions/${comp.id}/export.zip`}>
              Export package
            </a>
            <p>
              {comp.variants.some((v) => !v.final)
                ? `Export images skips frames without finals: ${comp.variants
                    .filter((v) => !v.final)
                    .map((v) => v.name)
                    .join(", ")}`
                : "Every frame final is included."}
            </p>
          </WorkspaceMenu>
          <WorkspaceMenu label="⋯">
            <ActionButton
              role="menuitem"
              disabled={toolbar.pending}
              onClick={() =>
                toolbarAction(async () => {
                  await autosave.flush();
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
            <button
              role="menuitem"
              disabled={toolbar.pending}
              onClick={() => setMoving(true)}
            >
              Move to project…
            </button>
            <ActionButton
              role="menuitem"
              disabled={
                toolbar.pending ||
                (comp.kind === "storyboard" && comp.variants.length > 1)
              }
              onClick={() =>
                patch({
                  kind: comp.kind === "single" ? "storyboard" : "single",
                })
              }
            >
              {comp.kind === "single" ? "Make storyboard" : "Make single image"}
            </ActionButton>
            {comp.kind === "storyboard" && comp.variants.length > 1 && (
              <p>A single image needs exactly one frame.</p>
            )}
            <button
              role="menuitem"
              className="destructive"
              disabled={toolbar.pending}
              onClick={() => setConfirming(true)}
            >
              Delete…
            </button>
          </WorkspaceMenu>
        </div>
      </div>
      {sequencePollError && (
        <p className="error" role="alert">
          {sequencePollError}
        </p>
      )}
      {toolbar.pending && (
        <span role="status" className="action-status">
          Saving…
        </span>
      )}
      {toolbar.notice && (
        <span role="status" className="action-status">
          {toolbar.notice}
        </span>
      )}
      {toolbar.error && (
        <p role="alert" className="error">
          {toolbar.error}
        </p>
      )}
      {moving && (
        <div className="panel">
          <label>
            Move to project
            <ActionSelect
              disabled={toolbar.pending}
              value={comp.project_id ?? ""}
              onChange={(e) =>
                patch({
                  project_id: e.target.value ? Number(e.target.value) : null,
                })
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
          <button onClick={() => setMoving(false)}>Done moving</button>
        </div>
      )}
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
                await autosave.flush();
                await api(`/compositions/${comp.id}`, "DELETE");
                window.location.hash = "compositions";
              })
            }
          >
            Yes, delete composition
          </ActionButton>
          <button onClick={() => setConfirming(false)}>Cancel</button>
        </div>
      )}
      {comp.kind === "storyboard" && (
        <Storyboard
          comp={comp}
          setComp={setComp}
          act={act}
          selected={variant.id}
          navigate={navigate}
          flush={autosave.flush}
        />
      )}
      <div className="workspace-columns">
        <CompositionSetup
          projectName={
            projects.find((p) => p.id === comp.project_id)?.name ||
            "Project assets"
          }
          {...{
            comp,
            setComp,
            variant,
            act,
            autosave,
            assets,
            references,
            warnings,
            draft,
            setDraft,
          }}
          previousFrame={preview?.previous_frame}
          current={preview?.references ?? []}
        />
        <div className="workspace-results" aria-label="Results">
          {previewError && (
            <p className="error" role="alert">
              {previewError}
            </p>
          )}
          <Runs
            key={variant.id}
            variantId={variant.id}
            {...{ act, refresh }}
            revision={`${revision}:${sequence?.frames?.map((f) => f.run_id + f.state).join() || ""}`}
            workspace
            queuedRun={queuedRun}
            reuse={(run) => {
              if (draft === null) remembered.current = { choices, format };
              const settings = runSettings(run, true);
              setDraft(run.references.map((r) => ({ ...r })));
              setChoices(settings.choices);
              setFormat(settings.format);
              setDraftContent(run.generations[0].assembled_prompt);
              setReusedAt(new Date(run.created_at).toLocaleString());
            }}
          />
        </div>
      </div>
      <div className="generate-bar" ref={bar}>
        {comp.kind === "storyboard" &&
          selectedIndex > 0 &&
          variant.use_previous_frame !== false &&
          !references.some((r) => r.role === "previous frame") && (
            <p role="status">
              No previous-frame image is available; this frame will run without
              it.
            </p>
          )}
        {sequence?.error && (
          <p role="alert" className="error">
            Sequence failed: {sequence.error}
          </p>
        )}
        {activeSequence && (
          <div className="actions">
            <span role="status">
              Sequence{" "}
              {sequence.state === "stopping"
                ? "stops after this frame"
                : "running"}
            </span>
            <ActionButton
              type="button"
              disabled={sequence.state === "stopping"}
              onClick={() =>
                act(async () => {
                  await api(`/frame-sequences/${sequence.id}/stop`, "POST");
                  await refresh();
                })
              }
            >
              Stop sequence
            </ActionButton>
          </div>
        )}
        {draft !== null && (
          <div className="reuse-chip">
            Reused from {reusedAt} ·{" "}
            <button
              type="button"
              className="plain"
              onClick={() => {
                setDraft(null);
                setDraftContent("");
                setChoices(remembered.current.choices);
                setFormat(remembered.current.format);
              }}
            >
              Back to current
            </button>
          </div>
        )}
        <ActionForm
          success="Run queued."
          onSubmit={(e) => {
            e.preventDefault();
            if (!canGenerate) return;
            act(async () => {
              await autosave.flush();
              const run = await api(`/variants/${variant.id}/runs`, "POST", {
                models: choices,
                format,
                ...(draft !== null
                  ? { references: draft, content: draftContent }
                  : {}),
              });
              setQueuedRun(run);
              setRevision((n) => n + 1);
            });
          }}
        >
          <div
            ref={(node) => {
              form.current = node?.closest("form");
            }}
            className="generate-controls"
          >
            <ModelRequests
              {...{ models, choices, setChoices, format, setFormat, revision }}
              workspace
              content={draft !== null ? draftContent : preview?.prompt}
              references={references}
              onPreview={setRendered}
            />
            <ActionButton className="primary" disabled={!canGenerate}>
              Generate
            </ActionButton>
            {comp.kind === "storyboard" && (
              <WorkspaceMenu label="Sequence options" above>
                {[
                  ["full", "Generate the full sequence", comp.variants.length],
                  [
                    "next",
                    "Generate the next frame",
                    selectedIndex + 1 < comp.variants.length ? 1 : 0,
                  ],
                  [
                    "rest",
                    "Generate the rest",
                    comp.variants.length - restIndex,
                  ],
                ].map(([mode, label, count]) => (
                  <ActionButton
                    type="button"
                    role="menuitem"
                    key={mode}
                    disabled={
                      !canGenerate ||
                      activeSequence ||
                      !count ||
                      draft !== null ||
                      choices.some((c) => c.prompt !== undefined)
                    }
                    onClick={() => startSequence(mode)}
                  >
                    {label} · {count} {count === 1 ? "frame" : "frames"} ·
                    estimated{" "}
                    {perFrameCost == null
                      ? "—"
                      : `$${(count * perFrameCost).toFixed(5)}`}
                  </ActionButton>
                ))}
                {(draft !== null ||
                  choices.some((c) => c.prompt !== undefined)) && (
                  <p>
                    Reset edited prompts and return to current references to
                    start a sequence.
                  </p>
                )}
              </WorkspaceMenu>
            )}
          </div>
        </ActionForm>
      </div>
    </section>
  );
}
