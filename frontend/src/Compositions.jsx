import { ActionButton, ActionForm, ActionInput, ActionSelect } from "./Actions";
import React, { useEffect, useState } from "react";
import { api } from "./api";
import { ProjectForm } from "./ProjectForm";
import { Sheet } from "./Sheet";
import { AssetTiles, AssetImage } from "./AssetTiles";
import { assetTypes } from "./AssetFields";

export function CompositionList({ items }) {
  return (
    <div className="image-grid composition-grid">
      {items.map((c) => (
        <a className="image-tile" key={c.id} href={`#composition/${c.id}`}>
          {c.thumbnail ? (
            <img
              className="tile-image"
              src={`/api/files/${c.thumbnail}`}
              alt={`${c.name} output`}
              loading="lazy"
            />
          ) : (
            <span className="tile-image thumbnail-empty">No output yet</span>
          )}
          <div className="tile-copy">
            <strong>{c.name}</strong>
            <p>
              {c.kind} · {c.frame_count}{" "}
              {c.frame_count === 1 ? "frame" : "frames"}
            </p>
            <small>
              Last activity {new Date(c.last_activity).toLocaleString()}
            </small>
          </div>
        </a>
      ))}
      {!items.length && <p>No compositions yet.</p>}
    </div>
  );
}

export function NewComposition({ projects, projectId, act }) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState("single");
  const [project, setProject] = useState(projectId ?? "");
  return (
    <ActionForm
      className="panel"
      onSubmit={(e) => {
        e.preventDefault();
        act(async () => {
          const c = await api("/compositions", "POST", {
            name,
            kind,
            project_id: project === "" ? null : Number(project),
          });
          window.location.hash = `composition/${c.id}`;
        });
      }}
    >
      <label>
        Name
        <ActionInput
          autoFocus
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <label>
        Kind
        <ActionSelect value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="single">Single image</option>
          <option value="storyboard">Storyboard</option>
        </ActionSelect>
      </label>
      <label>
        Project
        <ActionSelect
          value={project}
          onChange={(e) => setProject(e.target.value)}
        >
          <option value="">No project</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </ActionSelect>
      </label>
      <ActionButton className="primary">Create composition</ActionButton>
    </ActionForm>
  );
}

export function Compositions({
  projects,
  act,
  projectFilter = "",
  secondary = false,
}) {
  const [items, setItems] = useState([]);
  const [query, setQuery] = useState("");
  const [creating, setCreating] = useState(false);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    let active = true;
    setLoaded(false);
    act(async () => {
      const result = await api(
        `/compositions${projectFilter ? `?project_id=${projectFilter}` : ""}`,
      );
      if (active) {
        setItems(result);
        setLoaded(true);
      }
    }, false);
    return () => {
      active = false;
    };
  }, [projectFilter]);
  return (
    <section aria-label="Compositions">
      <div className="library-header">
        <h2>{projectFilter === "none" ? "No project" : "Compositions"}</h2>
        <ActionButton
          className={secondary || creating ? "secondary" : "primary"}
          onClick={() => setCreating(true)}
        >
          New composition
        </ActionButton>
      </div>
      <label className="list-search">
        Search compositions
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </label>
      {creating && (
        <Sheet title="New composition" onClose={() => setCreating(false)}>
          <NewComposition
            {...{ projects, act }}
            projectId={
              projectFilter && projectFilter !== "none"
                ? Number(projectFilter)
                : undefined
            }
          />
        </Sheet>
      )}
      {loaded ? (
        <CompositionList
          items={items.filter((c) =>
            c.name.toLowerCase().includes(query.toLowerCase()),
          )}
        />
      ) : (
        <p role="status">Loading compositions…</p>
      )}
    </section>
  );
}

function AddFromLibrary({ id, members, act, added }) {
  const [assets, setAssets] = useState([]);
  const [query, setQuery] = useState("");
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    let active = true;
    act(async () => {
      const result = await api("/assets?thumbnails=true");
      if (active) {
        setAssets(result);
        setLoaded(true);
      }
    }, false);
    return () => {
      active = false;
    };
  }, []);
  const choices = assets.filter(
    (a) =>
      !members.some((m) => m.id === a.id) &&
      a.name.toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <>
      <label>
        Search library
        <input
          autoFocus
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </label>
      <div className="library-picker">
        {choices.map((a) => (
          <ActionButton
            className="asset-pick"
            key={a.id}
            onClick={() =>
              act(async () => {
                await api(`/projects/${id}/assets/${a.id}`, "PUT");
                await added();
              })
            }
          >
            <AssetImage asset={a} />
            <span>
              {a.name} · {assetTypes[a.type]}
            </span>
          </ActionButton>
        ))}
        {loaded && !choices.length && <p>No matching assets.</p>}
      </div>
    </>
  );
}

export function ProjectPage({ id, projects, act, changed }) {
  const [project, setProject] = useState(null);
  const [members, setMembers] = useState([]);
  const [style, setStyle] = useState(null);
  const [editing, setEditing] = useState(false);
  const [adding, setAdding] = useState(false);
  const loadMembers = async () =>
    setMembers(await api(`/projects/${id}/assets`));
  useEffect(() => {
    let active = true;
    act(async () => {
      const [p, a] = await Promise.all([
        api(`/projects/${id}`),
        api(`/projects/${id}/assets`),
      ]);
      const s = p.style_asset_id
        ? await api(`/assets/${p.style_asset_id}?include_deleted=true`)
        : null;
      if (active) {
        setProject(p);
        setMembers(a);
        setStyle(s);
      }
    }, false);
    return () => {
      active = false;
    };
  }, [id, projects]);
  if (!project) return <p>Loading project…</p>;
  return (
    <section className="project-view" aria-label="Project">
      <header className="project-summary">
        <div className="library-header">
          <h2>{project.name}</h2>
          <button className="plain" onClick={() => setEditing(true)}>
            Edit
          </button>
        </div>
        <h3>Creative direction</h3>
        <p className="creative-direction">
          {project.instructions || "No creative direction yet."}
        </p>
        <h3>Style</h3>
        {style ? (
          <a className="project-style" href={`#asset/${style.id}`}>
            {(style.references[0] || style.originals[0]) && (
              <img
                src={`/api/files/${(style.references[0] || style.originals[0]).hash}`}
                alt=""
              />
            )}
            <span>
              {style.name}
              {style.deleted_at ? " · deleted" : ""}
            </span>
          </a>
        ) : (
          <p>No style</p>
        )}
      </header>
      {editing && (
        <Sheet title="Edit project" onClose={() => setEditing(false)}>
          <ProjectForm
            {...{ project, act, changed }}
            onSaved={() => setEditing(false)}
          />
        </Sheet>
      )}
      <Compositions
        {...{ projects, act }}
        projectFilter={id}
        secondary={editing}
      />
      <section aria-label="Project assets">
        <div className="library-header">
          <h2>Assets</h2>
          <ActionButton onClick={() => setAdding(true)}>
            Add from library
          </ActionButton>
        </div>
        <AssetTiles assets={members}>
          {(a) => (
            <ActionButton
              className="plain destructive"
              onClick={() =>
                act(async () => {
                  await api(`/projects/${id}/assets/${a.id}`, "DELETE");
                  await loadMembers();
                })
              }
            >
              Remove from project
            </ActionButton>
          )}
        </AssetTiles>
        {!members.length && <p>No project assets yet.</p>}
        {adding && (
          <Sheet title="Add from library" onClose={() => setAdding(false)}>
            <AddFromLibrary {...{ id, members, act }} added={loadMembers} />
          </Sheet>
        )}
      </section>
    </section>
  );
}
