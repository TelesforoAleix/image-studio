import { outputHref } from "./OutputViewer";
import { ActionGroup, ActionButton, ActionForm, ActionInput } from "./Actions";
import React, { useEffect, useState } from "react";
import { api } from "./api";
import { AssetFields, assetValues } from "./AssetFields";
import { ReferenceGeneration } from "./Generation";
export function AssetPage({ id, projects, act, changed }) {
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
        <a href="#assets">Back to Assets</a>
      </div>
      <ActionForm
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
        <ActionButton>Save asset</ActionButton>
      </ActionForm>
      <div className="panel">
        <label>
          <ActionInput
            type="checkbox"
            checked={showRejected}
            onChange={(e) => {
              setShowRejected(e.target.checked);
              act(async () =>
                setAsset(
                  await api(
                    `/assets/${id}?include_rejected=${e.target.checked}`,
                  ),
                ),
              );
            }}
          />
          Show rejected candidates
        </label>
        {[
          ["References", asset.references],
          ["Originals", asset.originals],
          [
            "Candidates waiting for review",
            asset.images.filter((i) => i.source === "generated" && !i.approved),
          ],
        ].map(([title, images]) => (
          <section key={title}>
            <h3>{title}</h3>
            {title === "Originals" && (
              <p>
                Uploads are sent only when ticked. Approve one to use it as a
                reference by default.
              </p>
            )}
            {title === "Originals" && (
              <ActionForm
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
                  <ActionInput
                    type="file"
                    name="files"
                    multiple
                    required
                    accept="image/jpeg,image/png,image/webp"
                  />
                </label>
                <p>
                  JPEG, PNG or WebP. Up to 25 MB per file and 90 MB per request.
                </p>
                <ActionButton className="primary">
                  Upload selected images
                </ActionButton>
              </ActionForm>
            )}
            {images.length ? (
              <div className="image-grid">
                {images.map((image) => (
                  <article
                    className={`image-card ${image.approved ? "canonical" : ""}`}
                    key={image.id}
                  >
                    <a
                      data-output={image.lineage ? true : undefined}
                      href={
                        image.lineage
                          ? outputHref(
                              image.lineage.generation_id,
                              image.lineage.output,
                            )
                          : `/api/files/${image.hash}`
                      }
                      target={image.lineage ? undefined : "_blank"}
                      rel="noreferrer"
                    >
                      <img
                        src={`/api/files/${image.hash}`}
                        alt={`Reference ${image.id} for ${asset.name}`}
                        loading="lazy"
                      />
                    </a>
                    <ActionGroup className="image-info">
                      <strong>
                        {image.rejected
                          ? "Rejected"
                          : image.approved
                            ? "Reference"
                            : "Not approved"}
                      </strong>
                      <small>
                        {image.width} × {image.height} · {image.source}
                      </small>
                      {image.lineage && (
                        <div className="lineage">
                          <small>
                            From originals · generation{" "}
                            {image.lineage.generation_id}
                          </small>
                          {image.lineage.originals.map((ref, index) => (
                            <a
                              key={index}
                              href={`/api/files/${ref.hash}`}
                              target={image.lineage ? undefined : "_blank"}
                              rel="noreferrer"
                            >
                              <img
                                src={`/api/files/${ref.hash}`}
                                alt={`Original ${index + 1}`}
                                loading="lazy"
                              />
                            </a>
                          ))}
                        </div>
                      )}
                      <ActionButton
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
                      </ActionButton>
                      {image.source === "generated" && !image.rejected && (
                        <ActionButton
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
                        </ActionButton>
                      )}
                    </ActionGroup>
                  </article>
                ))}
              </div>
            ) : (
              <p className="empty-note">No images in this list yet.</p>
            )}
          </section>
        ))}
      </div>
      <ReferenceGeneration
        inputRevision={[
          asset.name,
          asset.type_tag,
          asset.type,
          asset.description,
          asset.preserve,
          asset.images
            .filter((i) => i.source === "uploaded")
            .map((i) => i.hash)
            .join(","),
        ].join("|")}
        id={id}
        act={act}
        refresh={async () =>
          setAsset(await api(`/assets/${id}?include_rejected=${showRejected}`))
        }
      />
      <div className="panel actions">
        <a href={`/api/assets/${id}/export.zip`}>Export asset</a>
        <ActionButton
          onClick={() =>
            act(async () => {
              const copy = await api(`/assets/${id}/duplicate`, "POST");
              changed("Asset duplicated.");
              window.location.hash = `asset/${copy.id}`;
            })
          }
        >
          Duplicate asset
        </ActionButton>
        {!confirming ? (
          <ActionButton
            className="destructive"
            onClick={() => setConfirming(true)}
          >
            Delete asset…
          </ActionButton>
        ) : (
          <div className="delete-confirm">
            <p>
              Delete “{asset.name}” from Assets? Its record and images remain
              stored.
            </p>
            <ActionButton
              className="destructive"
              onClick={() =>
                act(async () => {
                  await api(`/assets/${id}`, "DELETE");
                  changed("Asset deleted.");
                  window.location.hash = "assets";
                })
              }
            >
              Yes, delete asset
            </ActionButton>
            <ActionButton
              className="plain"
              onClick={() => setConfirming(false)}
            >
              Cancel
            </ActionButton>
          </div>
        )}
      </div>
    </section>
  );
}
