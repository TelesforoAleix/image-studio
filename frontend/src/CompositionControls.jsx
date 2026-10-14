import React, { useState } from "react";
import { api } from "./api";

export function Selection({ selection, save, remove, busy }) {
  const [role, setRole] = useState(selection.role);
  return (
    <div className="panel">
      <h3>{selection.asset.name}</h3>
      <label>
        Role
        <input
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
          .filter((i) => i.approved && !i.rejected)
          .map((i) => (
            <label key={i.id}>
              <img src={`/api/files/${i.hash}`} alt={selection.asset.name} />
              <span>
                <input
                  type="checkbox"
                  disabled={busy}
                  checked={!selection.deselected_images.includes(i.id)}
                  onChange={(e) =>
                    save({
                      ...selection,
                      deselected_images: e.target.checked
                        ? selection.deselected_images.filter((x) => x !== i.id)
                        : [...selection.deselected_images, i.id],
                    })
                  }
                />
                Use reference {i.id}
              </span>
            </label>
          ))}
      </div>
      <button type="button" disabled={busy} onClick={remove}>
        Remove asset
      </button>
    </div>
  );
}

export function Storyboard({
  comp,
  setComp,
  act,
  busy,
  selected,
  tab,
  navigate,
}) {
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
    <div className="panel">
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
              <button
                disabled={busy || index === 0}
                onClick={() => move(index, -1)}
              >
                Move up
              </button>
              <button
                disabled={busy || index === comp.variants.length - 1}
                onClick={() => move(index, 1)}
              >
                Move down
              </button>
              <button
                className="danger"
                disabled={busy || comp.variants.length === 1}
                onClick={() => setConfirming(v.id)}
              >
                Delete frame…
              </button>
            </div>
          </article>
        ))}
      </div>
      <button
        disabled={busy}
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
      </button>
      {confirming && (
        <div className="delete-confirm">
          <p>
            Hide this frame with its runs and final? All files remain stored.
          </p>
          <button
            className="danger"
            disabled={busy}
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
          </button>
          <button onClick={() => setConfirming(null)}>Cancel</button>
        </div>
      )}
    </div>
  );
}
