import { ActionButton, ActionForm, ActionInput, ActionSelect } from "./Actions";
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
      <h3>New composition</h3>
      <label>
        Name
        <ActionInput
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
      {projectId == null && (
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
      )}
      <ActionButton className="primary">Create composition</ActionButton>
    </ActionForm>
  );
}

export function Compositions({ projects, act, projectFilter = "" }) {
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
        <ActionButton
          className={creating ? "secondary" : "primary"}
          onClick={() => setCreating(!creating)}
        >
          {creating ? "Close form" : "New composition"}
        </ActionButton>
      </div>
      <label>
        Project
        <ActionSelect
          value={project}
          onChange={(e) => setProject(e.target.value)}
        >
          <option value="">All projects</option>
          <option value="none">No project</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </ActionSelect>
      </label>
      {creating && <NewComposition {...{ projects, act }} />}
      <CompositionList items={items} />
    </section>
  );
}

export function ProjectPage({ id, projects, act, changed }) {
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
      <ProjectForm {...{ project, act, changed }} />
      <a href={`#assets?used_by_project=${id}`}>
        Assets used by this project's compositions
      </a>
      <h3>Compositions</h3>
      <CompositionList items={items} />
      <NewComposition {...{ projects, act }} projectId={Number(id)} />
    </section>
  );
}
