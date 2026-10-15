import { FieldHelp, guidance } from "./FieldHelp";
import { ActionButton, ActionInput, ActionTextarea } from "./Actions";
import React, { useEffect, useId, useState } from "react";
import { api } from "./api";
import { StylePicker } from "./StylePicker";
import { Selection } from "./CompositionControls";
import { PinnedReferences } from "./Runs";
import { assetTypes } from "./AssetFields";

export function CompositionSetup({
  comp,
  setComp,
  variant,
  act,
  autosave,
  assets,
  references,
  warnings,
  draft,
  setDraft,
  current,
}) {
  const helpId = useId();
  const [picker, setPicker] = useState(false);
  const [query, setQuery] = useState("");
  const [thumbnails, setThumbnails] = useState({});
  const [pickerError, setPickerError] = useState("");
  useEffect(() => {
    if (!picker) return;
    let active = true;
    Promise.all(
      assets
        .filter((a) => a.type !== "style")
        .map((a) => api(`/assets/${a.id}`)),
    )
      .then((details) => {
        if (active)
          setThumbnails(
            Object.fromEntries(details.map((a) => [a.id, a.images[0]?.hash])),
          );
      })
      .catch((e) => {
        if (active) setPickerError(e.message);
      });
    return () => {
      active = false;
    };
  }, [picker, assets]);
  const patch = (value) =>
    act(async () =>
      setComp(await api(`/compositions/${comp.id}`, "PATCH", value)),
    );
  const selections = [
    ...comp.assets,
    ...(comp.style
      ? [
          {
            asset: comp.style,
            deselected_images: comp.style_deselected_images,
            selected_originals: [],
            style: true,
          },
        ]
      : []),
  ];
  const frameImages = selections.flatMap((s) =>
    s.asset.images
      .filter(
        (i) =>
          !i.rejected &&
          !s.deselected_images.includes(i.id) &&
          (i.approved || (!s.style && i.source === "uploaded")),
      )
      .map((i) => ({
        ...i,
        asset: s.asset,
        defaultOn: i.approved || s.selected_originals.includes(i.id),
      })),
  );
  const field = (key, label, rows, help) => (
    <div key={key} className="autosave-field help-field">
      <div className="field-heading">
        <label htmlFor={`${helpId}-${key}`}>{label}</label>{" "}
        {help && <FieldHelp label={label} help={help} />}
      </div>
      <small role="status">{autosave.status[key] || "Saved"}</small>
      {rows ? (
        <ActionTextarea
          id={`${helpId}-${key}`}
          aria-label={label}
          rows={rows}
          value={autosave.value[key]}
          onChange={(e) => autosave.change(key, e.target.value)}
        />
      ) : (
        <ActionInput
          id={`${helpId}-${key}`}
          aria-label={label}
          required
          value={autosave.value[key]}
          onChange={(e) => autosave.change(key, e.target.value)}
        />
      )}
    </div>
  );
  return (
    <aside className="inspector" aria-label="Composition inspector">
      <h3>Asset pack</h3>
      {comp.assets.map((s) => (
        <Selection
          key={s.id}
          selection={s}
          save={(next) =>
            act(async () =>
              setComp(
                await api(
                  `/compositions/${comp.id}/assets/${s.asset_id}`,
                  "PUT",
                  {
                    role: next.role,
                    deselected_images: next.deselected_images,
                    selected_originals: next.selected_originals,
                  },
                ),
              ),
            )
          }
          remove={() =>
            act(async () =>
              setComp(
                await api(
                  `/compositions/${comp.id}/assets/${s.asset_id}`,
                  "DELETE",
                ),
              ),
            )
          }
        />
      ))}
      <button
        type="button"
        aria-expanded={picker}
        onClick={() => setPicker(!picker)}
      >
        Add asset
      </button>
      {picker && (
        <div className="asset-picker" aria-label="Asset picker">
          {pickerError && <p role="alert">{pickerError}</p>}
          <label>
            Search assets
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          {assets
            .filter(
              (a) =>
                a.type !== "style" &&
                !comp.assets.some((s) => s.asset_id === a.id) &&
                a.name.toLowerCase().includes(query.toLowerCase()),
            )
            .map((a) => (
              <ActionButton
                type="button"
                key={a.id}
                className="asset-pick"
                onClick={() =>
                  act(async () => {
                    setComp(
                      await api(
                        `/compositions/${comp.id}/assets/${a.id}`,
                        "PUT",
                        { role: a.name },
                      ),
                    );
                    setPicker(false);
                  })
                }
              >
                {thumbnails[a.id] && (
                  <img src={`/api/files/${thumbnails[a.id]}`} alt="" />
                )}
                <span>
                  {a.name} · {assetTypes[a.type]}
                </span>
              </ActionButton>
            ))}
          <button type="button" onClick={() => setPicker(false)}>
            Close picker
          </button>
        </div>
      )}
      <details className="pack-row">
        <summary className="pack-heading">
          {comp.style?.images[0] && (
            <img src={`/api/files/${comp.style.images[0].hash}`} alt="" />
          )}
          Style · {comp.style?.name || "None"}
        </summary>
        <StylePicker
          value={comp.style_asset_id}
          inherit
          act={act}
          onChange={(style_asset_id) =>
            patch({ style_asset_id, style_deselected_images: [] })
          }
        />
        <div className="reference-toggles">
          {comp.style?.images
            .filter((i) => i.approved && !i.rejected)
            .map((i, index, images) => (
              <label key={i.id}>
                <img src={`/api/files/${i.hash}`} alt={comp.style.name} />
                <span>
                  <ActionInput
                    type="checkbox"
                    checked={!comp.style_deselected_images.includes(i.id)}
                    onChange={(e) =>
                      patch({
                        style_deselected_images: e.target.checked
                          ? comp.style_deselected_images.filter(
                              (x) => x !== i.id,
                            )
                          : [...comp.style_deselected_images, i.id],
                      })
                    }
                  />
                  {comp.style.name}, reference {index + 1} of {images.length}
                </span>
              </label>
            ))}
        </div>
      </details>
      {field("name", "Composition name")}
      {field("brief", "Brief", 5, guidance[comp.kind])}
      {comp.kind === "storyboard" && (
        <>
          {field("frameName", "Frame name")}
          {field(
            "instructions",
            "What happens in this frame",
            3,
            guidance.frame,
          )}
          <details>
            <summary>This frame only</summary>
            <div className="reference-toggles">
              {frameImages.map((i, index) => (
                <label key={i.id}>
                  <img src={`/api/files/${i.hash}`} alt={i.asset.name} />
                  <span>
                    <ActionInput
                      type="checkbox"
                      checked={
                        (i.defaultOn ||
                          variant.selected_originals.includes(i.id)) &&
                        !variant.deselected_images.includes(i.id)
                      }
                      onChange={(e) =>
                        act(async () => {
                          const deselected = variant.deselected_images.filter(
                            (x) =>
                              frameImages.some((i) => i.id === x) && x !== i.id,
                          );
                          const originals = variant.selected_originals.filter(
                            (x) => x !== i.id,
                          );
                          if (!e.target.checked && i.defaultOn)
                            deselected.push(i.id);
                          if (e.target.checked && !i.approved && !i.defaultOn)
                            originals.push(i.id);
                          await api(`/variants/${variant.id}`, "PATCH", {
                            deselected_images: deselected,
                            selected_originals: originals,
                          });
                          setComp(await api(`/compositions/${comp.id}`));
                        })
                      }
                    />
                    {i.asset.name}, {i.approved ? "reference" : "original"}{" "}
                    {frameImages
                      .filter(
                        (x) =>
                          x.asset.id === i.asset.id &&
                          x.approved === i.approved,
                      )
                      .indexOf(i) + 1}{" "}
                    of{" "}
                    {
                      frameImages.filter(
                        (x) =>
                          x.asset.id === i.asset.id &&
                          x.approved === i.approved,
                      ).length
                    }
                  </span>
                </label>
              ))}
            </div>
          </details>
        </>
      )}
      {draft !== null && (
        <PinnedReferences draft={draft} setDraft={setDraft} current={current} />
      )}
      <p className="reference-total">{references.length} references selected</p>
      {warnings.map((w) => (
        <p className="limit-warning" role="alert" key={w}>
          {w}
        </p>
      ))}
    </aside>
  );
}
