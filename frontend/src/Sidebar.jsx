import React, { useEffect, useState } from "react";
import { api } from "./api";

const types = {
  person: "People",
  garment_product: "Garments/Products",
  object_vehicle: "Objects/Vehicles",
  environment: "Environments",
  style: "Styles",
  other: "Other",
};
export function Sidebar({
  base,
  projects,
  newProject,
  act,
  compositionProject,
}) {
  const [spend, setSpend] = useState(null);
  const compositionId = /^composition\/(\d+)/.exec(base)?.[1];
  useEffect(() => {
    let active = true;
    act(async () => {
      const value = await api("/spend");
      if (active) setSpend(value.estimated_spend);
    }, false);
    return () => {
      active = false;
    };
  }, [base]);
  const selected = compositionId
    ? compositionProject === undefined
      ? ""
      : compositionProject === null
        ? "studio/none"
        : `studio/project/${compositionProject}`
    : base.startsWith("asset/")
      ? "assets"
      : base;
  const link = (route, label, className) => (
    <a
      key={route}
      className={className}
      href={`#${route}`}
      aria-current={selected === route ? "page" : undefined}
    >
      {label}
    </a>
  );
  return (
    <aside className="studio-sidebar" aria-label="Sidebar">
      <h1>
        <a href="#studio">
          image studio
          <span className="studio-dot" aria-hidden="true">
            .
          </span>
        </a>
      </h1>
      <nav aria-label="Workspace">
        <div className="sidebar-group">
          <h2>Studio</h2>
          {link("studio", "All compositions")}
          {link("studio/none", "No project")}
          {projects.map((p) =>
            link(`studio/project/${p.id}`, p.name, "folder-link"),
          )}
          <button className="plain" onClick={newProject}>
            + New project
          </button>
        </div>
        <div className="sidebar-group">
          <h2>Assets</h2>
          {link("assets", "All assets")}
          {Object.entries(types).map(([key, label]) =>
            link(`assets/${key}`, label),
          )}
        </div>
      </nav>
      <footer>
        <p>
          This month’s estimated spend
          <br />
          {spend === null ? "Loading…" : `$${Number(spend).toFixed(2)}`}
        </p>
        {link("storage", "Storage", "secondary-link")}
      </footer>
    </aside>
  );
}
