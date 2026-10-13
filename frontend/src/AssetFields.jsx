import React from "react";
export function AssetFields({ value, onChange, projects }) {
  const field = (name, next) => onChange({ ...value, [name]: next });
  return (
    <>
      <label>
        Name
        <input
          required
          value={value.name}
          onChange={(e) => field("name", e.target.value)}
        />
      </label>
      <label>
        Type tag <span>(optional)</span>
        <input
          value={value.type_tag || ""}
          onChange={(e) => field("type_tag", e.target.value)}
          placeholder="For example, garment"
        />
      </label>
      <label>
        Description
        <textarea
          rows="5"
          value={value.description}
          onChange={(e) => field("description", e.target.value)}
        />
      </label>
      <label>
        Visibility
        <select
          value={value.project_id ?? ""}
          onChange={(e) =>
            field("project_id", e.target.value ? Number(e.target.value) : null)
          }
        >
          <option value="">Global — every project</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </label>
    </>
  );
}
export const blankAsset = () => ({
  name: "",
  type_tag: "",
  description: "",
  project_id: null,
});
export const assetValues = (asset) => ({
  name: asset.name,
  type_tag: asset.type_tag,
  description: asset.description,
  project_id: asset.project_id,
});
