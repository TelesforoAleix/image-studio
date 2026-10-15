import { ActionSelect } from "./Actions";
import React, { useEffect, useState } from "react";
import { api } from "./api";

export function StylePicker({ value, onChange, act, inherit = false }) {
  const [styles, setStyles] = useState([]);
  useEffect(() => {
    act(async () => setStyles(await api("/assets?type=style")), false);
  }, [value]);
  return (
    <label>
      Style
      <ActionSelect
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
    </label>
  );
}
