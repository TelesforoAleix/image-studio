import React, { useEffect, useState } from "react";
import { api } from "./api";
import { ProjectForm } from "./ProjectForm";
import { History, ModelPicker } from "./Generation";

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

export function CompositionPage({ id, act, busy }) {
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
  const [model, setModel] = useState("");
  const [count, setCount] = useState(1);
  const [revision, setRevision] = useState(0);
  const variant = comp?.variants[0];
  useEffect(() => {
    act(async () => {
      const c = await api(`/compositions/${id}`);
      setComp(c);
      setScene(c.scene);
      setInstructions(c.variants[0].instructions);
      setAssets(await api(`/assets?project_id=${c.project_id}`));
      setModels(await api("/models"));
    }, false);
  }, [id]);
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
        await api(`/compositions/${id}/assets/${s.asset_id}`, "PUT", {
          role: s.role,
          deselected_images: s.deselected_images,
        }),
      ),
    );
  async function saveText() {
    await api(`/compositions/${id}`, "PATCH", { scene });
    await api(`/variants/${variant.id}`, "PATCH", { instructions });
  }
  const available = assets.filter(
    (a) => !comp.assets.some((s) => s.asset_id === a.id),
  );
  return (
    <section>
      <div className="library-header">
        <h2>{comp.name}</h2>
        <a href={`#project/${comp.project_id}`}>Back to project</a>
      </div>
      <form
        className="panel"
        onSubmit={(e) => {
          e.preventDefault();
          act(saveText);
        }}
      >
        <label>
          Scene instructions
          <textarea
            rows="5"
            value={scene}
            onChange={(e) => setScene(e.target.value)}
          />
        </label>
        <label>
          Frame 1 instructions
          <textarea
            rows="3"
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
          />
        </label>
        <button disabled={busy}>Save instructions</button>
      </form>
      <form
        className="panel"
        onSubmit={(e) => {
          e.preventDefault();
          act(async () => {
            setComp(
              await api(`/compositions/${id}/assets/${assetId}`, "PUT", {
                role,
              }),
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
                await api(`/compositions/${id}/assets/${s.asset_id}`, "DELETE"),
              ),
            )
          }
        />
      ))}
      <div className="panel">
        <h3>Prompt to send</h3>
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
            onClick={() => {
              setEditing(false);
              setEdited("");
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
              await api(`/variants/${variant.id}/generations`, "POST", {
                model,
                count,
                prompt: editing ? edited : preview.prompt,
              });
              setRevision((n) => n + 1);
            });
          }}
        >
          <ModelPicker
            {...{ models, model, setModel, count, setCount }}
            references={preview?.references.length || 0}
          />
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
            Generate
          </button>
        </form>
      </div>
      <h3>Frame 1 results</h3>
      <History
        path={`/variants/${variant.id}/generations`}
        {...{ act, revision }}
      />
    </section>
  );
}
