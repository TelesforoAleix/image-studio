import React, { useEffect, useState } from "react";
import { api } from "./api";
import { ProjectForm } from "./ProjectForm";

export function CompositionList({ items }) {
  return (
    <div className="composition-list">
      {items.map((c) => (
        <a className="composition-row" key={c.id} href={`#composition/${c.id}`}>
          {c.thumbnail ? (
            <img src={`/api/files/${c.thumbnail}`} alt={`${c.name} output`} />
          ) : (
            <span className="thumbnail-empty">No output yet</span>
          )}
          <div>
            <strong>{c.name}</strong>
            <p>
              {c.kind} · {c.project?.name ?? "No project"}
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

export function NewComposition({ projects, projectId, act, busy }) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState("single");
  const [project, setProject] = useState(projectId ?? "");
  return (
    <form
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
      <h3>New composition</h3>
      <label>
        Name
        <input
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <label>
        Kind
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="single">Single image</option>
          <option value="storyboard">Storyboard</option>
        </select>
      </label>
      {projectId == null && (
        <label>
          Project
          <select value={project} onChange={(e) => setProject(e.target.value)}>
            <option value="">No project</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
      )}
      <button disabled={busy}>Create composition</button>
    </form>
  );
}

export function Compositions({ projects, act, busy, projectFilter = "" }) {
  const [items, setItems] = useState([]);
  const [project, setProject] = useState(projectFilter);
  const [creating, setCreating] = useState(false);
  useEffect(() => {
    act(
      async () =>
        setItems(
          await api(`/compositions${project ? `?project_id=${project}` : ""}`),
        ),
      false,
    );
  }, [project]);
  return (
    <section>
      <div className="library-header">
        <h2>Compositions</h2>
        <button onClick={() => setCreating(!creating)}>
          {creating ? "Close form" : "New composition"}
        </button>
      </div>
      <label>
        Project
        <select value={project} onChange={(e) => setProject(e.target.value)}>
          <option value="">All projects</option>
          <option value="none">No project</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </label>
      {creating && <NewComposition {...{ projects, act, busy }} />}
      <CompositionList items={items} />
    </section>
  );
}

export function ProjectPage({ id, projects, act, changed, busy }) {
  const [project, setProject] = useState(null);
  const [items, setItems] = useState([]);
  useEffect(() => {
    act(async () => {
      setProject(await api(`/projects/${id}`));
      setItems(await api(`/projects/${id}/compositions`));
    }, false);
  }, [id, projects]);
  if (!project) return <p>Loading project…</p>;
  return (
    <section>
      <div className="library-header">
        <h2>{project.name}</h2>
        <a href="#projects">Projects</a>
      </div>
      <ProjectForm {...{ project, act, changed, busy }} />
      <a href={`#assets?used_by_project=${id}`}>
        Assets used by this project's compositions
      </a>
      <h3>Compositions</h3>
      <CompositionList items={items} />
      <NewComposition {...{ projects, act, busy }} projectId={Number(id)} />
    </section>
  );
}
