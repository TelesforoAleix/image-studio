import React, { useEffect, useState } from "react";
import { api } from "./api";
import { AssetFields, blankAsset } from "./AssetFields";
export function Library({ projects, act, revision, busy, projectFilter = "" }) {
  const [assets, setAssets] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [tag, setTag] = useState("");
  const [project, setProject] = useState(projectFilter);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState(blankAsset);
  useEffect(() => setProject(projectFilter), [projectFilter]);
  useEffect(() => {
    let active = true;
    setLoaded(false);
    const query = new URLSearchParams();
    if (tag) query.set("type_tag", tag);
    if (project) query.set("used_by_project", project);
    act(async () => {
      const result = await api(`/assets?${query}`);
      if (active) {
        setAssets(result);
        setLoaded(true);
      }
    }, false);
    return () => {
      active = false;
    };
  }, [tag, project, revision]);
  return (
    <section aria-labelledby="library-title">
      <div className="library-header">
        <h2 id="library-title">Assets</h2>
        <button onClick={() => setCreating(!creating)}>
          {creating ? "Close form" : "New asset"}
        </button>
      </div>
      <div className="filters">
        <label>
          Type tag
          <input
            value={tag}
            onChange={(e) => setTag(e.target.value)}
            placeholder="All types"
          />
        </label>
        <label>
          Project view
          <select value={project} onChange={(e) => setProject(e.target.value)}>
            <option value="">All assets</option>

            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                Used by {p.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {creating && (
        <form
          className="panel"
          onSubmit={(e) => {
            e.preventDefault();
            act(async () => {
              const result = await api("/assets", "POST", draft);
              window.location.hash = `asset/${result.id}`;
            });
          }}
        >
          <h3>Create asset</h3>
          <AssetFields value={draft} onChange={setDraft} projects={projects} />
          <button disabled={busy}>Create asset</button>
        </form>
      )}
      {!loaded ? (
        <p role="status">Loading assets…</p>
      ) : assets.length ? (
        <>
          <p className="asset-count">
            {assets.length} {assets.length === 1 ? "asset" : "assets"}
          </p>
          <div className="asset-list">
            {assets.map((asset) => (
              <a
                className="asset-card"
                key={asset.id}
                href={`#asset/${asset.id}`}
              >
                <h3>{asset.name}</h3>
                <span className="badge">{asset.type_tag || "No type tag"}</span>
                <p>
                  {asset.description || "Add a description and references."}
                </p>
                <small>Global</small>
              </a>
            ))}
          </div>
        </>
      ) : (
        <div className="empty-library">
          <span className="empty-mark" aria-hidden="true">
            +
          </span>
          <h3>{tag || project ? "No matching assets" : "No assets yet"}</h3>
          <p>
            Your reusable people, garments, objects and backgrounds will live
            here.
          </p>
        </div>
      )}
    </section>
  );
}
