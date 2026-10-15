import { FieldHelp, guidance } from "./FieldHelp";
import { ActionSelect } from "./Actions";
import React, { useEffect, useId, useState } from "react";
import { api } from "./api";

export function StylePicker({ value, onChange, act, inherit = false }) {
  const helpId = useId();
  const [styles, setStyles] = useState([]);
  useEffect(() => {
    act(async () => setStyles(await api("/assets?type=style")), false);
  }, [value]);
  return (
    <div className="help-field">
      <div className="field-heading">
        <label htmlFor={`${helpId}-style`}>Style</label>{" "}
        <FieldHelp label="Style" help={guidance.style} />
      </div>
      <ActionSelect
        id={`${helpId}-style`}
        aria-label="Style"
        value={value ?? ""}
        onChange={(e) =>
          onChange(e.target.value ? Number(e.target.value) : null)
        }
      >
        <option value="">
          {inherit ? "Use project style (if set)" : "No style"}
        </option>
        {value && !styles.some((s) => s.id === value) && (
          <option value={value} disabled>
            Unavailable style
          </option>
        )}
        {styles.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name}
          </option>
        ))}
      </ActionSelect>
    </div>
  );
}
