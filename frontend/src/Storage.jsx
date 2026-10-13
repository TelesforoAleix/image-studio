import React, { useEffect, useState } from "react";
import { api } from "./api";

function size(bytes) {
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${units[unit]}`;
}

export function Storage({ act, busy }) {
  const [usage, setUsage] = useState(null);
  const load = () => act(async () => setUsage(await api("/storage")), false);
  useEffect(() => {
    load();
  }, []);
  return (
    <section>
      <div className="library-header">
        <h2>Storage used</h2>
        <button disabled={busy} onClick={load}>
          Refresh
        </button>
      </div>
      <p className="intro">
        All stored images are retained, including earlier references, rejected
        candidates and outputs from hidden assets and frames. Shared files
        count once.
      </p>
      {usage ? (
        <div className="asset-list">
          {[
            ["total", "Total images"],
            ["uploaded", "Uploaded images"],
            ["generated", "Generated images"],
            ["placeholder", "Placeholder output"],
          ].map(([key, label]) => (
            <article className="panel storage-card" key={key}>
              <h3>{label}</h3>
              <strong>{size(usage[key].bytes)}</strong>
              <p>
                {usage[key].file_count.toLocaleString()} files ·{" "}
                {usage[key].bytes.toLocaleString()} bytes
              </p>
            </article>
          ))}
        </div>
      ) : (
        <p role="status">Loading storage figures…</p>
      )}
      <p className="intro">
        These figures cover image files, excluding the database and backups.
        Exports add no stored files. Permanent deletion is not available.
      </p>
    </section>
  );
}
