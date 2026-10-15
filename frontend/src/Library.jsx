import { ActionButton, ActionForm } from "./Actions";
import React, { useEffect, useState } from "react";
import { api } from "./api";
import { AssetFields, blankAsset } from "./AssetFields";
import { Sheet } from "./Sheet";
import { AssetTiles } from "./AssetTiles";

export function Library({ projects, act, revision, type = "" }) {
  const [assets, setAssets] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [query, setQuery] = useState("");
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState(blankAsset);
  useEffect(() => {
    let active = true;
    setLoaded(false);
    act(async () => {
      const params = new URLSearchParams({ thumbnails: "true" });
      if (type) params.set("type", type);
      const result = await api(`/assets?${params}`);
      if (active) {
        setAssets(result);
        setLoaded(true);
      }
    }, false);
    return () => {
      active = false;
    };
  }, [type, revision]);
  const filtered = assets.filter((a) =>
    a.name.toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <section aria-labelledby="library-title">
      <div className="library-header">
        <h2 id="library-title">Assets</h2>
        <ActionButton
          className={creating ? "secondary" : "primary"}
          onClick={() => {
            setDraft(blankAsset());
            setCreating(true);
          }}
        >
          New asset
        </ActionButton>
      </div>
      <label className="list-search">
        Search assets
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </label>
      {creating && (
        <Sheet title="New asset" onClose={() => setCreating(false)}>
          <ActionForm
            className="panel"
            onSubmit={(e) => {
              e.preventDefault();
              act(async () => {
                const result = await api("/assets", "POST", draft);
                window.location.hash = `asset/${result.id}`;
              });
            }}
          >
            <AssetFields
              value={draft}
              onChange={setDraft}
              projects={projects}
            />
            <ActionButton className="primary">Create asset</ActionButton>
          </ActionForm>
        </Sheet>
      )}
      {!loaded ? (
        <p role="status">Loading assets…</p>
      ) : (
        <>
          <p className="asset-count">
            {filtered.length} {filtered.length === 1 ? "asset" : "assets"}
          </p>
          <AssetTiles assets={filtered} />
          {!filtered.length && (
            <div className="empty-library">
              <h3>{query || type ? "No matching assets" : "No assets yet"}</h3>
              <p>
                Your reusable people, garments, objects and backgrounds will
                live here.
              </p>
            </div>
          )}
        </>
      )}
    </section>
  );
}
