import React from "react";
import { api } from "./api";
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
  busy,
  available,
  assetId,
  setAssetId,
  role,
  setRole,
  setComp,
  saveSelection,
  variant,
}) {
  return (
    <>
      <form
        className="panel"
        onSubmit={(e) => {
          e.preventDefault();
          act(saveText);
        }}
      >
        <>
          <label>
            Composition name
            <input
              required
              value={compName}
              onChange={(e) => setCompName(e.target.value)}
            />
          </label>
          <label>
            Composition creative direction
            <textarea
              rows="4"
              value={direction}
              onChange={(e) => setDirection(e.target.value)}
            />
          </label>
          <label>
            Scene
            <textarea
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
              <input
                required
                value={frameName}
                onChange={(e) => setFrameName(e.target.value)}
              />
            </label>
            <label>
              Frame instructions
              <textarea
                rows="3"
                value={instructions}
                onChange={(e) => setInstructions(e.target.value)}
              />
            </label>
          </>
        }
        <button disabled={busy}>Save instructions</button>
      </form>
      {
        <>
          <h3>Shared asset pack · all frames</h3>
          <form
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
              <select
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
              </select>
            </label>
            <label>
              Role
              <input
                required
                value={role}
                onChange={(e) => setRole(e.target.value)}
                placeholder="For example, the background"
              />
            </label>
            <button disabled={busy || !assetId}>Add asset</button>
          </form>
          {comp.assets.map((s) => (
            <Selection
              key={s.id}
              selection={s}
              save={saveSelection}
              busy={busy}
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
            <p>Switch off selected pack images for this frame only.</p>
            <div className="reference-toggles">
              {comp.assets.flatMap((s) =>
                s.asset.images
                  .filter(
                    (i) =>
                      i.approved &&
                      !i.rejected &&
                      !s.deselected_images.includes(i.id),
                  )
                  .map((i) => (
                    <label key={i.id}>
                      <img src={`/api/files/${i.hash}`} alt={s.asset.name} />
                      <span>
                        <input
                          type="checkbox"
                          disabled={busy}
                          checked={!variant.deselected_images.includes(i.id)}
                          onChange={(e) =>
                            act(async () => {
                              const available = comp.assets.flatMap((s) =>
                                s.asset.images
                                  .filter(
                                    (i) =>
                                      i.approved &&
                                      !i.rejected &&
                                      !s.deselected_images.includes(i.id),
                                  )
                                  .map((i) => i.id),
                              );
                              const deselected =
                                variant.deselected_images.filter(
                                  (x) => available.includes(x) && x !== i.id,
                                );
                              if (!e.target.checked) deselected.push(i.id);
                              await api(`/variants/${variant.id}`, "PATCH", {
                                deselected_images: deselected,
                              });
                              setComp(await api(`/compositions/${comp.id}`));
                            })
                          }
                        />
                        Use {s.asset.name} reference {i.id}
                      </span>
                    </label>
                  )),
              )}
            </div>
          </div>
        </>
      }
    </>
  );
}
