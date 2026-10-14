import React from "react";
export const assetTypes = {
  person: "Person",
  garment_product: "Garment/Product",
  object_vehicle: "Object/Vehicle",
  environment: "Environment",
  style: "Style",
  other: "Other",
};
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
        Type
        <select
          required
          value={value.type}
          onChange={(e) => field("type", e.target.value)}
        >
          {Object.entries(assetTypes).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label>
        Label <span>(optional)</span>
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
        What must stay the same
        <textarea
          rows="4"
          value={value.preserve}
          onChange={(e) => field("preserve", e.target.value)}
        />
      </label>
    </>
  );
}
export const blankAsset = () => ({
  name: "",
  type: "other",
  preserve: "",
  type_tag: "",
  description: "",
});
export const assetValues = (asset) => ({
  name: asset.name,
  type: asset.type,
  preserve: asset.preserve,
  type_tag: asset.type_tag,
  description: asset.description,
});
