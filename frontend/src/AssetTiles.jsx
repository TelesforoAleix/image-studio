import React from "react";
import { assetTypes } from "./AssetFields";

export function AssetImage({ asset }) {
  return asset.thumbnail ? (
    <img
      className="tile-image"
      src={`/api/files/${asset.thumbnail}`}
      alt=""
      loading="lazy"
    />
  ) : (
    <span className="tile-image thumbnail-empty">No image yet</span>
  );
}

export function AssetTiles({ assets, children }) {
  return (
    <div className="image-grid asset-grid">
      {assets.map((asset) => (
        <article className="image-tile" key={asset.id}>
          <a href={`#asset/${asset.id}`}>
            <AssetImage asset={asset} />
            <div className="tile-copy">
              <strong>{asset.name}</strong>
              <p>
                {assetTypes[asset.type]}
                {asset.deleted_at ? " · deleted" : ""}
              </p>
            </div>
          </a>
          {children?.(asset)}
        </article>
      ))}
    </div>
  );
}
