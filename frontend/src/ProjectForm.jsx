import { FieldHelp, guidance } from "./FieldHelp";
import {
  ActionButton,
  ActionForm,
  ActionInput,
  ActionTextarea,
} from "./Actions";
import React, { useId, useState } from "react";
import { StylePicker } from "./StylePicker";
import { api } from "./api";
export function ProjectForm({ project, act, changed, onSaved }) {
  const helpId = useId();
  const [name, setName] = useState(project?.name || "");
  const [instructions, setInstructions] = useState(project?.instructions || "");
  const [style, setStyle] = useState(project?.style_asset_id ?? null);
  return (
    <ActionForm
      className="panel"
      onSubmit={(e) => {
        e.preventDefault();
        act(async () => {
          const saved = await api(
            project ? `/projects/${project.id}` : "/projects",
            project ? "PATCH" : "POST",
            { name, instructions, style_asset_id: style },
          );
          if (!project) {
            setName("");
            setInstructions("");
          }
          changed("Project saved.");
          onSaved?.(saved);
          if (!project) window.location.hash = `studio/project/${saved.id}`;
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
      <div className="help-field">
        <div className="field-heading">
          <label htmlFor={`${helpId}-creative`}>Creative direction</label>{" "}
          <FieldHelp label="Creative direction" help={guidance.creative} />
        </div>
        <ActionTextarea
          id={`${helpId}-creative`}
          aria-label="Creative direction"
          rows="5"
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
          placeholder="Shared creative instructions for this project"
        />
      </div>
      <StylePicker value={style} onChange={setStyle} {...{ act }} />
      <ActionButton className="primary">
        {project ? "Save" : "Create project"}
      </ActionButton>
    </ActionForm>
  );
}
