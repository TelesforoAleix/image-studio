import { FieldHelp, guidance } from "./FieldHelp";
import { ActionInput, ActionSelect, ActionTextarea } from "./Actions";
import React, { useId } from "react";
export const assetTypes = {
  person: "Person",
  garment_product: "Garment/Product",
  object_vehicle: "Object/Vehicle",
  environment: "Environment",
  style: "Style",
  other: "Other",
};
export function AssetFields({ value, onChange }) {
  const helpId = useId();
  const field = (name, next) => onChange({ ...value, [name]: next });
  return (
    <>
      <label>
        Name
        <ActionInput
          required
          value={value.name}
          onChange={(e) => field("name", e.target.value)}
        />
      </label>
      <label>
        Type
        <ActionSelect
          required
          value={value.type}
          onChange={(e) => field("type", e.target.value)}
        >
          {Object.entries(assetTypes).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </ActionSelect>
      </label>
      <label>
        Label <span>(optional)</span>
        <ActionInput
          value={value.type_tag || ""}
          onChange={(e) => field("type_tag", e.target.value)}
          placeholder="For example, garment"
        />
      </label>
      <div className="help-field">
        <div className="field-heading">
          <label htmlFor={`${helpId}-description`}>Description</label>{" "}
          <FieldHelp label="Description" help={guidance.description} />
        </div>
        <ActionTextarea
          id={`${helpId}-description`}
          aria-label="Description"
          rows="5"
          value={value.description}
          onChange={(e) => field("description", e.target.value)}
        />
      </div>
      <div className="help-field">
        <div className="field-heading">
          <label htmlFor={`${helpId}-preserve`}>What must stay the same</label>{" "}
          <FieldHelp label="What must stay the same" help={guidance.preserve} />
        </div>
        <ActionTextarea
          id={`${helpId}-preserve`}
          aria-label="What must stay the same"
          rows="4"
          value={value.preserve}
          onChange={(e) => field("preserve", e.target.value)}
        />
      </div>
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
