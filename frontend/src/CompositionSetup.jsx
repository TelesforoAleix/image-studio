import {
  ActionButton,
  ActionForm,
  ActionInput,
  ActionSelect,
  ActionTextarea,
} from "./Actions";
import React from "react";
import { api } from "./api";
import { StylePicker } from "./StylePicker";
import { Selection } from "./CompositionControls";

export function CompositionSetup({
  comp,
  compName,
  setCompName,
  direction,
  setDirection,
  scene,
  setScene,
  frameName,
  setFrameName,
  instructions,
  setInstructions,
  act,
  saveText,
  available,
  assetId,
  setAssetId,
  role,
  setRole,
  setComp,
  saveSelection,
  variant,
}) {
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
  return (
    <>
      <div className="panel">
        <StylePicker
          value={comp.style_asset_id}
          inherit
          {...{ act }}
          onChange={(style_asset_id) =>
            act(async () =>
              setComp(
                await api(`/compositions/${comp.id}`, "PATCH", {
                  style_asset_id,
                  style_deselected_images: [],
                }),
              ),
            )
          }
        />
        {comp.style && (
          <>
            <p>Using {comp.style.name}</p>
            <div className="reference-toggles">
              {comp.style.images
                .filter((i) => i.approved && !i.rejected)
                .map((i) => (
                  <label key={i.id}>
                    <img src={`/api/files/${i.hash}`} alt={comp.style.name} />
                    <span>
                      <ActionInput
                        type="checkbox"
                        checked={!comp.style_deselected_images.includes(i.id)}
                        onChange={(e) =>
                          act(async () =>
                            setComp(
                              await api(`/compositions/${comp.id}`, "PATCH", {
                                style_deselected_images: e.target.checked
                                  ? comp.style_deselected_images.filter(
                                      (x) => x !== i.id,
                                    )
                                  : [...comp.style_deselected_images, i.id],
                              }),
                            ),
                          )
                        }
                      />
                      Use style reference {i.id}
                    </span>
                  </label>
                ))}
            </div>
          </>
        )}
      </div>
      <ActionForm
        className="panel"
        onSubmit={(e) => {
          e.preventDefault();
          act(saveText);
        }}
      >
        <>
          <label>
            Composition name
            <ActionInput
              required
              value={compName}
              onChange={(e) => setCompName(e.target.value)}
            />
          </label>
          <label>
            Composition creative direction
            <ActionTextarea
              rows="4"
              value={direction}
              onChange={(e) => setDirection(e.target.value)}
            />
          </label>
          <label>
            Scene
            <ActionTextarea
              rows="5"
              value={scene}
              onChange={(e) => setScene(e.target.value)}
            />
          </label>
        </>
        {
          <>
            <label>
              Frame name
              <ActionInput
                required
                value={frameName}
                onChange={(e) => setFrameName(e.target.value)}
              />
            </label>
            <label>
              Frame instructions
              <ActionTextarea
                rows="3"
                value={instructions}
                onChange={(e) => setInstructions(e.target.value)}
              />
            </label>
          </>
        }
        <ActionButton className="primary">Save instructions</ActionButton>
      </ActionForm>
      {
        <>
          <h3>Shared asset pack · all frames</h3>
          <ActionForm
            className="panel"
            onSubmit={(e) => {
              e.preventDefault();
              act(async () => {
                setComp(
                  await api(
                    `/compositions/${comp.id}/assets/${assetId}`,
                    "PUT",
                    {
                      role,
                    },
                  ),
                );
                setAssetId("");
                setRole("");
              });
            }}
          >
            <h3>Add an asset</h3>
            <label>
              Assets
              <ActionSelect
                required
                value={assetId}
                onChange={(e) => setAssetId(e.target.value)}
              >
                <option value="">Choose an asset</option>
                {available.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </ActionSelect>
            </label>
            <label>
              Role
              <ActionInput
                required
                value={role}
                onChange={(e) => setRole(e.target.value)}
                placeholder="For example, the background"
              />
            </label>
            <ActionButton disabled={!assetId}>Add asset</ActionButton>
          </ActionForm>
          {comp.assets.map((s) => (
            <Selection
              key={s.id}
              selection={s}
              save={saveSelection}
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
        </>
      }
      {
        <>
          <div className="panel">
            <h3>References for this frame</h3>
            <p>Choose references and optional originals for this frame only.</p>
            <div className="reference-toggles">
              {frameImages.map((i) => (
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
                    Use {i.asset.name} {i.approved ? "reference" : "original"}{" "}
                    {i.id}
                  </span>
                </label>
              ))}
            </div>
          </div>
        </>
      }
    </>
  );
}
