import React, { useEffect, useState } from "react";
import { api } from "./api";
import { AssetFields, assetValues } from "./AssetFields";
import { ReferenceGeneration } from "./Generation";
export function AssetPage({ id, projects, act, changed, busy }) {
  const [asset, setAsset] = useState(null);
  const [draft, setDraft] = useState(null);
  const [showRejected, setShowRejected] = useState(false);
  const [confirming, setConfirming] = useState(false);
  useEffect(() => {
    let active = true;
    act(async () => {
      const result = await api(`/assets/${id}`);
      if (active) {
        setAsset(result);
        setDraft(assetValues(result));
      }
    }, false);
    return () => {
      active = false;
    };
  }, [id]);
  if (!asset)
    return (
      <section>
        <p role="status">Loading asset…</p>
      </section>
    );
  return (
    <section>
      <div className="library-header">
        <h2>{asset.name}</h2>
        <a href="#library">Back to library</a>
      </div>
      <form
        className="panel"
        onSubmit={(e) => {
          e.preventDefault();
          act(async () => {
            setAsset(await api(`/assets/${id}`, "PATCH", draft));
            changed("Asset saved.");
          });
        }}
      >
        <AssetFields value={draft} onChange={setDraft} projects={projects} />
        <button disabled={busy}>Save asset</button>
      </form>
      <div className="panel">
        <h3>Reference images</h3>
        <p>
          Approve images to make them canonical references. Unapproved images
          remain attached.
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const form = e.currentTarget;
            const body = new FormData(form);
            act(async () => {
              setAsset(await api(`/assets/${id}/images`, "POST", body));
              form.reset();
              changed("Images uploaded.");
            });
          }}
        >
          <label>
            Upload images
            <input
              type="file"
              name="files"
              multiple
              required
              accept="image/jpeg,image/png,image/webp"
            />
          </label>
          <p>JPEG, PNG or WebP. Up to 25 MB per file and 90 MB per request.</p>
          <button disabled={busy}>Upload selected images</button>
        </form>
        <label>
          <input
            type="checkbox"
            checked={showRejected}
            onChange={(e) => {
              setShowRejected(e.target.checked);
              act(
                async () =>
                  setAsset(
                    await api(
                      `/assets/${id}?include_rejected=${e.target.checked}`,
                    ),
                  ),
                false,
              );
            }}
          />
          Show rejected candidates
        </label>
        {asset.images.length ? (
          <div className="image-grid">
            {asset.images.map((image) => (
              <article
                className={`image-card ${image.approved ? "canonical" : ""}`}
                key={image.id}
              >
                <a
                  href={`/api/files/${image.hash}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  <img
                    src={`/api/files/${image.hash}`}
                    alt={`Reference ${image.id} for ${asset.name}`}
                    loading="lazy"
                  />
                </a>
                <div className="image-info">
                  <strong>
                    {image.rejected
                      ? "Rejected"
                      : image.approved
                        ? "Canonical reference"
                        : "Not approved"}
                  </strong>
                  <small>
                    {image.width} × {image.height} · {image.source}
                  </small>
                  <button
                    disabled={busy}
                    type="button"
                    onClick={() =>
                      act(async () => {
                        setAsset(
                          await api(
                            `/assets/${id}/images/${image.id}`,
                            "PATCH",
                            { approved: !image.approved },
                          ),
                        );
                        changed(
                          image.approved
                            ? "Reference unapproved."
                            : "Reference approved.",
                        );
                      })
                    }
                  >
                    {image.approved ? "Unapprove" : "Approve"}
                  </button>
                  {image.source === "generated" && !image.rejected && (
                    <button
                      disabled={busy}
                      onClick={() =>
                        act(async () => {
                          setAsset(
                            await api(
                              `/assets/${id}/images/${image.id}?include_rejected=${showRejected}`,
                              "PATCH",
                              { rejected: true },
                            ),
                          );
                          changed("Candidate rejected.");
                        })
                      }
                    >
                      Reject
                    </button>
                  )}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <p className="empty-note">No reference images yet.</p>
        )}
      </div>
      <ReferenceGeneration
        inputRevision={asset.images
          .filter((i) => i.source === "uploaded")
          .map((i) => i.hash)
          .join(",")}
        id={id}
        act={act}
        busy={busy}
        refresh={async () =>
          setAsset(await api(`/assets/${id}?include_rejected=${showRejected}`))
        }
      />
      <div className="panel actions">
        <button
          disabled={busy}
          onClick={() =>
            act(async () => {
              const copy = await api(`/assets/${id}/duplicate`, "POST");
              changed("Asset duplicated.");
              window.location.hash = `asset/${copy.id}`;
            })
          }
        >
          Duplicate asset
        </button>
        {!confirming ? (
          <button className="danger" onClick={() => setConfirming(true)}>
            Delete asset…
          </button>
        ) : (
          <div className="delete-confirm">
            <p>
              Delete “{asset.name}” from the library? Its record and images
              remain stored.
            </p>
            <button
              className="danger"
              disabled={busy}
              onClick={() =>
                act(async () => {
                  await api(`/assets/${id}`, "DELETE");
                  changed("Asset deleted.");
                  window.location.hash = "library";
                })
              }
            >
              Yes, delete asset
            </button>
            <button onClick={() => setConfirming(false)}>Cancel</button>
          </div>
        )}
      </div>
    </section>
  );
}
