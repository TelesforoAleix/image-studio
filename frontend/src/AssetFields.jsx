import React from "react";
export function AssetFields({ value, onChange }) {
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
    </>
  );
}
export const blankAsset = () => ({
  name: "",
  type_tag: "",
  description: "",
});
export const assetValues = (asset) => ({
  name: asset.name,
  type_tag: asset.type_tag,
  description: asset.description,
});
