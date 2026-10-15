import { FieldHelp, guidance } from "./FieldHelp";
import { ActionGroup, ActionButton, ActionInput } from "./Actions";
import React, { useId, useState } from "react";
import { WorkspaceMenu } from "./WorkspaceMenu";
import { api } from "./api";

export function Selection({ selection, save, remove }) {
  const helpId = useId();
  const [role, setRole] = useState(selection.role);
  return (
    <ActionGroup className="pack-row">
      <div className="pack-heading">
        {selection.asset.images[0] && (
          <img src={`/api/files/${selection.asset.images[0].hash}`} alt="" />
        )}
        <strong>{selection.asset.name}</strong>
      </div>
      <div className="help-field">
        <div className="field-heading">
          <label htmlFor={`${helpId}-role`}>Role</label>{" "}
          <FieldHelp label="Role" help={guidance.role} />
        </div>
        <ActionInput
          id={`${helpId}-role`}
          aria-label="Role"
          value={role}
          onChange={(e) => setRole(e.target.value)}
          onBlur={() => {
            if (role !== selection.role) save({ ...selection, role });
          }}
        />
      </div>
      {selection.asset.deleted_at && (
        <p>This asset was deleted. Remove it to generate.</p>
      )}
      <details>
        <summary>Images</summary>
        <div className="reference-toggles">
          {selection.asset.images
            .filter(
              (i) => !i.rejected && (i.approved || i.source === "uploaded"),
            )
            .map((i, index, images) => (
              <label key={i.id}>
                <img src={`/api/files/${i.hash}`} alt={selection.asset.name} />
                <span>
                  <ActionInput
                    type="checkbox"
                    checked={
                      i.approved
                        ? !selection.deselected_images.includes(i.id)
                        : selection.selected_originals.includes(i.id)
                    }
                    onChange={(e) =>
                      save({
                        ...selection,
                        ...(i.approved
                          ? {
                              deselected_images: e.target.checked
                                ? selection.deselected_images.filter(
                                    (x) => x !== i.id,
                                  )
                                : [...selection.deselected_images, i.id],
                            }
                          : {
                              selected_originals: e.target.checked
                                ? [...selection.selected_originals, i.id]
                                : selection.selected_originals.filter(
                                    (x) => x !== i.id,
                                  ),
                            }),
                      })
                    }
                  />
                  {selection.asset.name},{" "}
                  {i.approved ? "reference" : "original"}{" "}
                  {images.filter((x) => x.approved === i.approved).indexOf(i) +
                    1}{" "}
                  of {images.filter((x) => x.approved === i.approved).length}
                </span>
              </label>
            ))}
        </div>
        <ActionButton className="plain" type="button" onClick={remove}>
          Remove asset
        </ActionButton>
      </details>
    </ActionGroup>
  );
}

export function Storyboard({ comp, setComp, act, selected, navigate, flush }) {
  const [confirming, setConfirming] = useState(null);
  const [dragged, setDragged] = useState(null);
  const [orderError, setOrderError] = useState("");
  const reorder = (ids) =>
    act(async () => {
      await flush();
      setOrderError("");
      setComp(
        await api(`/compositions/${comp.id}/frame-order`, "PUT", { ids }),
      );
    }).catch((e) => setOrderError(e.message));
  const move = (index, delta) =>
    act(async () => {
      await flush();
      setOrderError("");
      const ids = comp.variants.map((v) => v.id);
      [ids[index], ids[index + delta]] = [ids[index + delta], ids[index]];
      setComp(
        await api(`/compositions/${comp.id}/frame-order`, "PUT", { ids }),
      );
    }).catch((e) => setOrderError(e.message));
  return (
    <ActionGroup className="filmstrip">
      {orderError && (
        <p role="alert" className="error">
          {orderError}
        </p>
      )}
      <div className="frame-strip">
        {comp.variants.map((v, index) => (
          <article
            className="frame-card"
            key={v.id}
            draggable
            onDragStart={(e) => {
              setDragged(v.id);
              e.dataTransfer.setData("text/plain", String(v.id));
            }}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              const source =
                Number(e.dataTransfer.getData("text/plain")) || dragged;
              const ids = comp.variants
                .map((f) => f.id)
                .filter((id) => id !== source);
              if (
                source === v.id ||
                !comp.variants.some((f) => f.id === source)
              )
                return;
              ids.splice(ids.indexOf(v.id), 0, source);
              reorder(ids);
              setDragged(null);
            }}
            onKeyDown={(e) => {
              const delta =
                e.key === "ArrowLeft" ? -1 : e.key === "ArrowRight" ? 1 : 0;
              if (e.altKey && delta && comp.variants[index + delta]) {
                e.preventDefault();
                move(index, delta);
              }
            }}
          >
            <a
              href={`#composition/${comp.id}/frame/${v.id}`}
              aria-current={v.id === selected ? "page" : undefined}
            >
              {v.final ? (
                <img
                  src={`/api/files/${v.final.hash}`}
                  alt={`${v.name} final`}
                />
              ) : (
                <span className="thumbnail-empty">No final yet</span>
              )}
              <strong>
                {index + 1}. {v.name}
              </strong>
            </a>
            <div className="actions">
              <ActionButton
                className="plain"
                aria-label="Move up"
                disabled={index === 0}
                onClick={() => move(index, -1)}
              >
                ←
              </ActionButton>
              <ActionButton
                className="plain"
                aria-label="Move down"
                disabled={index === comp.variants.length - 1}
                onClick={() => move(index, 1)}
              >
                →
              </ActionButton>
              <WorkspaceMenu label={`Frame menu: ${v.name}`} icon="⋯">
                <ActionButton
                  role="menuitem"
                  className="destructive"
                  disabled={comp.variants.length === 1}
                  onClick={() => setConfirming(v.id)}
                >
                  Delete frame…
                </ActionButton>
              </WorkspaceMenu>
            </div>
          </article>
        ))}
      </div>
      <ActionButton
        aria-label="Add frame"
        onClick={() =>
          act(async () => {
            await flush();
            const frame = await api(
              `/compositions/${comp.id}/variants`,
              "POST",
              {},
            );
            setComp(await api(`/compositions/${comp.id}`));
            await navigate(frame.id);
          })
        }
      >
        + Add frame
      </ActionButton>
      {confirming && (
        <div className="delete-confirm">
          <p>
            Hide this frame with its runs and final? All files remain stored.
          </p>
          <ActionButton
            className="destructive"
            onClick={() =>
              act(async () => {
                await flush();
                await api(`/variants/${confirming}`, "DELETE");
                const next = await api(`/compositions/${comp.id}`);
                setComp(next);
                if (confirming === selected)
                  await navigate(next.variants[0].id);
                setConfirming(null);
              })
            }
          >
            Yes, delete frame
          </ActionButton>
          <ActionButton className="plain" onClick={() => setConfirming(null)}>
            Cancel
          </ActionButton>
        </div>
      )}
    </ActionGroup>
  );
}
