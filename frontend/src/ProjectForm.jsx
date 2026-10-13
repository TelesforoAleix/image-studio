import React, { useState } from "react";
import { api } from "./api";
export function ProjectForm({ project, act, changed, busy }) {
  const [name, setName] = useState(project?.name || "");
  const [instructions, setInstructions] = useState(project?.instructions || "");
  return (
    <form
      className="panel"
      onSubmit={(e) => {
        e.preventDefault();
        act(async () => {
          await api(
            project ? `/projects/${project.id}` : "/projects",
            project ? "PATCH" : "POST",
            { name, instructions },
          );
          if (!project) {
            setName("");
            setInstructions("");
          }
          changed("Project saved.");
        });
      }}
    >
      <h3>{project ? project.name : "New project"}</h3>
      <label>
        Name
        <input
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <label>
        Creative direction
        <textarea
          rows="5"
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
          placeholder="Shared creative instructions for this project"
        />
      </label>
      <button disabled={busy}>
        {project ? "Save project" : "Create project"}
      </button>
    </form>
  );
}
