import { outputHref } from "./OutputViewer";
import { ActionGroup, ActionButton, ActionInput } from "./Actions";
import React, { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { AssetFields, assetTypes } from "./AssetFields";
import { ReferenceGeneration } from "./Generation";
import { GenerationProgress } from "./Progress";
import { WorkspaceMenu } from "./WorkspaceMenu";
import { useAutosave } from "./useAutosave";

export function AssetPage({ id, act, changed }) {
  const [asset, setAsset] = useState(null);
  useEffect(() => {
    let active = true;
    act(async () => {
      const next = await api(`/assets/${id}`);
      if (active) setAsset(next);
    }, false);
    return () => {
      active = false;
    };
  }, [id]);
  return asset ? (
    <AssetWorkspace {...{ id, asset, setAsset, act, changed }} />
  ) : (
    <p role="status">Loading asset…</p>
  );
}

function AssetWorkspace({ id, asset, setAsset, act, changed }) {
  const upload = useRef(null);
  const autosave = useAutosave(asset, {}, setAsset, true);
  const [showRejected, setShowRejected] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [bulk, setBulk] = useState(null);
  const [sheet, setSheet] = useState(false);
  const [runs, setRuns] = useState([]);
  const [reviewBusy, setReviewBusy] = useState(false);
  const refresh = async () =>
    setAsset(await api(`/assets/${id}?include_rejected=${showRejected}`));
  const candidates = asset.images.filter(
    (i) => i.source === "generated" && !i.approved && !i.rejected,
  );
  const pending = runs.filter((g) => ["waiting", "running"].includes(g.state));
  const review = async (images, values) => {
    setReviewBusy(true);
    try {
      for (const image of images)
        await api(`/assets/${id}/images/${image.id}`, "PATCH", values);
      setBulk(null);
      changed(
        values.rejected
          ? "Candidates rejected."
          : values.approved
            ? "References approved."
            : "Reference unapproved.",
      );
    } finally {
      try {
        await refresh();
      } finally {
        setReviewBusy(false);
      }
    }
  };
  const tiles = (images, candidate = false) => (
    <div
      className={`image-grid asset-images ${candidate ? "review-images" : ""}`}
    >
      {images.map((image) => (
        <ActionGroup
          as="article"
          className="image-card"
          key={image.id}
          tabIndex={candidate ? 0 : undefined}
          aria-label={`${candidate ? "Candidate" : "Image"} ${image.id}`}
          onKeyDown={(e) => {
            if (
              !candidate ||
              reviewBusy ||
              e.repeat ||
              e.altKey ||
              e.ctrlKey ||
              e.metaKey ||
              !["a", "r"].includes(e.key.toLowerCase())
            )
              return;
            e.preventDefault();
            e.currentTarget
              .querySelector(`[data-review="${e.key.toLowerCase()}"]`)
              ?.click();
          }}
        >
          <a
            data-output
            href={
              image.lineage
                ? outputHref(image.lineage.generation_id, image.lineage.output)
                : outputHref(0, image.id)
            }
          >
            <img
              src={`/api/files/${image.hash}`}
              alt={`Image ${image.id} for ${asset.name}`}
              loading="lazy"
            />
          </a>
          <div className="image-info">
            <small>
              {image.width} × {image.height} · {image.source}
            </small>
            <div className="actions">
              <ActionButton
                data-review="a"
                disabled={reviewBusy}
                onClick={() =>
                  act(() => review([image], { approved: !image.approved }))
                }
              >
                {image.approved ? "Unapprove" : "Approve"}
              </ActionButton>
              {image.source === "generated" && !image.rejected && (
                <ActionButton
                  data-review="r"
                  disabled={reviewBusy}
                  onClick={() => act(() => review([image], { rejected: true }))}
                >
                  Reject
                </ActionButton>
              )}
            </div>
          </div>
        </ActionGroup>
      ))}
      {!images.length && (
        <p className="empty-note">No images in this list yet.</p>
      )}
    </div>
  );
  return (
    <section className="asset-workspace">
      <header className="workspace-toolbar">
        <div className="breadcrumb">
          <a href="#assets">Assets</a>
          <span>›</span>
          <a href={`#assets/${asset.type}`}>{assetTypes[asset.type]}</a>
          <span>›</span>
          <h2>{asset.name}</h2>
        </div>
        <div className="actions">
          <WorkspaceMenu label="Share">
            <a role="menuitem" href={`/api/assets/${id}/export.zip`}>
              Export asset
            </a>
          </WorkspaceMenu>
          <WorkspaceMenu label="⋯">
            <ActionButton
              role="menuitem"
              onClick={() =>
                act(async () => {
                  await autosave.flush();
                  const copy = await api(`/assets/${id}/duplicate`, "POST");
                  changed("Asset duplicated.");
                  location.hash = `asset/${copy.id}`;
                })
              }
            >
              Duplicate asset
            </ActionButton>
            <ActionButton
              role="menuitem"
              className="destructive"
              onClick={() => setConfirming(true)}
            >
              Delete asset…
            </ActionButton>
          </WorkspaceMenu>
        </div>
      </header>
      {confirming && (
        <ActionGroup className="delete-confirm">
          <p>
            Delete “{asset.name}” from Assets? Its record and images remain
            stored.
          </p>
          <ActionButton
            className="destructive"
            onClick={() =>
              act(async () => {
                await autosave.flush();
                await api(`/assets/${id}`, "DELETE");
                changed("Asset deleted.");
                location.hash = "assets";
              })
            }
          >
            Yes, delete asset
          </ActionButton>
          <button onClick={() => setConfirming(false)}>Cancel</button>
        </ActionGroup>
      )}
      <div className="asset-columns">
        <div className="asset-main">
          <header className="library-header">
            <h3>Images</h3>
            <ActionButton
              className={sheet ? undefined : "primary"}
              onClick={() =>
                act(async () => {
                  await autosave.flush();
                  setSheet(true);
                })
              }
            >
              Generate reference views
            </ActionButton>
          </header>
          {(candidates.length > 0 || pending.length > 0) && (
            <section aria-label="To review">
              <div className="library-header">
                <h3>To review</h3>
                {candidates.length > 0 && (
                  <div className="actions">
                    {["Approve", "Reject"].map((action) => (
                      <ActionButton
                        key={action}
                        disabled={reviewBusy}
                        onClick={() =>
                          candidates.length > 1
                            ? setBulk(action)
                            : act(() =>
                                review(
                                  candidates,
                                  action === "Approve"
                                    ? { approved: true }
                                    : { rejected: true },
                                ),
                              )
                        }
                      >
                        {action} all
                      </ActionButton>
                    ))}
                  </div>
                )}
              </div>
              {bulk && (
                <ActionGroup className="bulk-confirm">
                  <p>
                    {bulk} all {candidates.length} candidates?
                  </p>
                  <ActionButton
                    disabled={reviewBusy}
                    onClick={() =>
                      act(() =>
                        review(
                          candidates,
                          bulk === "Approve"
                            ? { approved: true }
                            : { rejected: true },
                        ),
                      )
                    }
                  >
                    Yes, {bulk.toLowerCase()} all
                  </ActionButton>
                  <button onClick={() => setBulk(null)}>Cancel</button>
                </ActionGroup>
              )}
              {candidates.length > 0 && tiles(candidates, true)}
              <div className="image-grid asset-images review-images">
                {pending.flatMap((g) =>
                  Array.from(
                    { length: Math.max(0, g.count - g.outputs.length) },
                    (_, i) => (
                      <article
                        className="generation-placeholder image-card"
                        key={`${g.id}-${i}`}
                        aria-label="Generating reference"
                      >
                        <div className="placeholder-image">
                          {g.model_info.display_name}
                        </div>
                        <div className="image-info" role="status">
                          <GenerationProgress generation={g} />
                        </div>
                      </article>
                    ),
                  ),
                )}
              </div>
              <p className="secondary-text">
                Focus a candidate: A to approve · R to reject
              </p>
            </section>
          )}
          <section aria-label="References">
            <h3>References</h3>
            {tiles(asset.references.filter((i) => !i.rejected))}
          </section>
          <section
            aria-label="Originals"
            className="originals-drop"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              upload.current(e.dataTransfer.files);
            }}
          >
            <h3>Originals</h3>
            <p>
              Drop JPEG, PNG or WebP images here, up to 25 MiB each. Approve an
              original to use it as a reference by default.
            </p>
            <AssetUpload id={id} refresh={refresh} upload={upload} />
            {tiles(asset.originals.filter((i) => !i.rejected))}
          </section>
          <label className="rejected-toggle">
            <input
              type="checkbox"
              checked={showRejected}
              onChange={(e) => {
                const next = e.target.checked;
                setShowRejected(next);
                act(async () =>
                  setAsset(await api(`/assets/${id}?include_rejected=${next}`)),
                );
              }}
            />{" "}
            Show rejected
          </label>
          {showRejected && (
            <section aria-label="Rejected">
              <h3>Rejected</h3>
              {tiles(asset.images.filter((i) => i.rejected))}
            </section>
          )}
          <ReferenceGeneration
            {...{ id, act, refresh }}
            open={sheet}
            onClose={() => setSheet(false)}
            flush={autosave.flush}
            onItems={setRuns}
            images={asset.images}
            inputRevision={JSON.stringify([
              asset.name,
              asset.type,
              asset.type_tag,
              asset.description,
              asset.preserve,
              asset.originals.map((i) => i.hash),
            ])}
          />
        </div>
        <aside
          className="inspector asset-inspector"
          aria-label="Asset inspector"
        >
          <h3>Details</h3>
          <AssetFields
            value={autosave.value}
            status={autosave.status}
            onChange={(next) => {
              for (const key of Object.keys(next))
                if (next[key] !== autosave.value[key])
                  autosave.change(key, next[key]);
            }}
          />
        </aside>
      </div>
    </section>
  );
}

function AssetUpload({ id, refresh, upload }) {
  const picker = useRef(null);
  const [files, setFiles] = useState([]);
  const update = (key, values) =>
    setFiles((old) =>
      old.map((row) => (row.key === key ? { ...row, ...values } : row)),
    );
  const chain = useRef(Promise.resolve());
  upload.current = (incoming) => {
    for (const file of incoming) {
      const key = crypto.randomUUID();
      const allowed = ["image/jpeg", "image/png", "image/webp"].includes(
        file.type,
      );
      const error = !allowed
        ? "Choose JPEG, PNG or WebP."
        : file.size > 25 * 1024 * 1024
          ? "Maximum size is 25 MiB."
          : "";
      setFiles((old) => [...old, { key, name: file.name, progress: 0, error }]);
      if (error) continue;
      chain.current = chain.current
        .catch(() => {})
        .then(
          () =>
            new Promise((resolve) => {
              const xhr = new XMLHttpRequest();
              xhr.open("POST", `/api/assets/${id}/images`);
              xhr.upload.onprogress = (e) => {
                if (e.lengthComputable)
                  update(key, {
                    progress: Math.round((e.loaded / e.total) * 100),
                  });
              };
              xhr.onerror = () => {
                update(key, { error: "Upload failed. Try again." });
                resolve();
              };
              xhr.onload = async () => {
                try {
                  if (xhr.status < 200 || xhr.status >= 300)
                    throw new Error(
                      JSON.parse(xhr.responseText).error || "Upload failed.",
                    );
                  await refresh();
                  update(key, { progress: 100, done: true });
                } catch (e) {
                  update(key, { error: e.message });
                }
                resolve();
              };
              const body = new FormData();
              body.append("files", file);
              xhr.send(body);
            }),
        );
    }
  };
  return (
    <div className="asset-upload">
      <input
        ref={picker}
        type="file"
        multiple
        accept="image/jpeg,image/png,image/webp"
        aria-label="Upload images"
        hidden
        onChange={(e) => {
          upload.current(e.target.files);
          e.target.value = "";
        }}
      />
      <button onClick={() => picker.current.click()}>Upload</button>
      <ul>
        {files.map((file) => (
          <li key={file.key}>
            {file.name}{" "}
            {file.error ? (
              <span role="alert">{file.error}</span>
            ) : (
              <>
                <progress
                  aria-label={`Upload ${file.name}`}
                  value={file.progress}
                  max="100"
                />
                <span role="status">
                  {file.done ? "Uploaded" : `${file.progress}%`}
                </span>
              </>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
