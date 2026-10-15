import {
  ActionButton,
  ActionForm,
  ActionInput,
  ActionTextarea,
} from "./Actions";
import React, { useState } from "react";
import { StylePicker } from "./StylePicker";
import { api } from "./api";
export function ProjectForm({ project, act, changed }) {
  const [name, setName] = useState(project?.name || "");
  const [instructions, setInstructions] = useState(project?.instructions || "");
  const [style, setStyle] = useState(project?.style_asset_id ?? null);
  return (
    <ActionForm
      className="panel"
      onSubmit={(e) => {
        e.preventDefault();
        act(async () => {
          await api(
            project ? `/projects/${project.id}` : "/projects",
            project ? "PATCH" : "POST",
            { name, instructions, style_asset_id: style },
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
        <ActionInput
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <label>
        Creative direction
        <ActionTextarea
          rows="5"
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
          placeholder="Shared creative instructions for this project"
        />
      </label>
      <StylePicker value={style} onChange={setStyle} {...{ act }} />
      <ActionButton className={project ? "secondary" : "primary"}>
        {project ? "Save project" : "Create project"}
      </ActionButton>
    </ActionForm>
  );
}
