import { ActionGroup, ActionButton, ActionInput } from "./Actions";
import React, { useState } from "react";
import { api } from "./api";

export function Selection({ selection, save, remove }) {
  const [role, setRole] = useState(selection.role);
  return (
    <ActionGroup className="panel">
      <h3>{selection.asset.name}</h3>
      <label>
        Role
        <ActionInput
          value={role}
          onChange={(e) => setRole(e.target.value)}
          onBlur={() => {
            if (role !== selection.role) save({ ...selection, role });
          }}
        />
      </label>
      {selection.asset.deleted_at && (
        <p>This asset was deleted. Remove it to generate.</p>
      )}
      <div className="reference-toggles">
        {selection.asset.images
          .filter((i) => !i.rejected && (i.approved || i.source === "uploaded"))
          .map((i) => (
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
                Use {i.approved ? "reference" : "original"} {i.id}
              </span>
            </label>
          ))}
      </div>
      <ActionButton className="plain" type="button" onClick={remove}>
        Remove asset
      </ActionButton>
    </ActionGroup>
  );
}

export function Storyboard({ comp, setComp, act, selected, tab, navigate }) {
  const [confirming, setConfirming] = useState(null);
  const move = (index, delta) =>
    act(async () => {
      const ids = comp.variants.map((v) => v.id);
      [ids[index], ids[index + delta]] = [ids[index + delta], ids[index]];
      setComp(
        await api(`/compositions/${comp.id}/frame-order`, "PUT", { ids }),
      );
    });
  return (
    <ActionGroup className="panel">
      <div className="frame-strip">
        {comp.variants.map((v, index) => (
          <article className="frame-card" key={v.id}>
            <a
              href={`#composition/${comp.id}/frame/${v.id}/${tab}`}
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
                disabled={index === 0}
                onClick={() => move(index, -1)}
              >
                Move up
              </ActionButton>
              <ActionButton
                className="plain"
                disabled={index === comp.variants.length - 1}
                onClick={() => move(index, 1)}
              >
                Move down
              </ActionButton>
              <ActionButton
                className="destructive"
                disabled={comp.variants.length === 1}
                onClick={() => setConfirming(v.id)}
              >
                Delete frame…
              </ActionButton>
            </div>
          </article>
        ))}
      </div>
      <ActionButton
        onClick={() =>
          act(async () => {
            const frame = await api(
              `/compositions/${comp.id}/variants`,
              "POST",
              {},
            );
            setComp(await api(`/compositions/${comp.id}`));
            navigate("setup", frame.id);
          })
        }
      >
        Add frame
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
                await api(`/variants/${confirming}`, "DELETE");
                const next = await api(`/compositions/${comp.id}`);
                setComp(next);
                if (confirming === selected) navigate(tab, next.variants[0].id);
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
