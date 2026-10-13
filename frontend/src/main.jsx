import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

async function api(path, method = "GET", body) {
  const multipart = body instanceof FormData;
  const response = await fetch(`/api${path}`, {
    method,
    headers:
      body && !multipart ? { "Content-Type": "application/json" } : undefined,
    body: body ? (multipart ? body : JSON.stringify(body)) : undefined,
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "The request failed");
  return result;
}

function AssetFields({ value, onChange, projects }) {
  const field = (name, next) => onChange({ ...value, [name]: next });
  return (
    <>
      <label>
        Name
        <input
          required
          value={value.name}
          onChange={(e) => field("name", e.target.value)}
        />
      </label>
      <label>
        Type tag <span>(optional)</span>
        <input
          value={value.type_tag || ""}
          onChange={(e) => field("type_tag", e.target.value)}
          placeholder="For example, garment"
        />
      </label>
      <label>
        Description
        <textarea
          rows="5"
          value={value.description}
          onChange={(e) => field("description", e.target.value)}
        />
      </label>
      <label>
        Visibility
        <select
          value={value.project_id ?? ""}
          onChange={(e) =>
            field("project_id", e.target.value ? Number(e.target.value) : null)
          }
        >
          <option value="">Global — every project</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </label>
    </>
  );
}
const blankAsset = () => ({
  name: "",
  type_tag: "",
  description: "",
  project_id: null,
});
const assetValues = (asset) => ({
  name: asset.name,
  type_tag: asset.type_tag,
  description: asset.description,
  project_id: asset.project_id,
});

function Library({ projects, act, revision, busy }) {
  const [assets, setAssets] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [tag, setTag] = useState("");
  const [project, setProject] = useState("");
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState(blankAsset);
  useEffect(() => {
    let active = true;
    setLoaded(false);
    const query = new URLSearchParams();
    if (tag) query.set("type_tag", tag);
    if (project) query.set("project_id", project);
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
        <h2 id="library-title">Asset library</h2>
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
            <option value="global">Global only</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} + global
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
                <small>
                  {asset.project_id === null
                    ? "Global"
                    : projects.find((p) => p.id === asset.project_id)?.name}
                </small>
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

function ProjectForm({ project, act, changed, busy }) {
  const [name, setName] = useState(project?.name || "");
  const [instructions, setInstructions] = useState(project?.instructions || "");
  return (
    <form
      className="panel"
      onSubmit={(e) => {
        e.preventDefault();
        act(async () => {
          await api(
            project ? `/projects/${project.id}` : "/projects",
            project ? "PATCH" : "POST",
            { name, instructions },
          );
          if (!project) {
            setName("");
            setInstructions("");
          }
          changed("Project saved.");
        });
      }}
    >
      <h3>{project ? project.name : "New project"}</h3>
      <label>
        Name
        <input
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <label>
        Creative direction
        <textarea
          rows="5"
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
          placeholder="Shared creative instructions for this project"
        />
      </label>
      <button disabled={busy}>
        {project ? "Save project" : "Create project"}
      </button>
    </form>
  );
}

function AssetPage({ id, projects, act, changed, busy }) {
  const [asset, setAsset] = useState(null);
  const [draft, setDraft] = useState(null);
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
                    {image.approved ? "Canonical reference" : "Not approved"}
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
                </div>
              </article>
            ))}
          </div>
        ) : (
          <p className="empty-note">No reference images yet.</p>
        )}
      </div>
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

function App() {
  const [route, setRoute] = useState(
    window.location.hash.slice(1) || "library",
  );
  const [projects, setProjects] = useState([]);
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(0);
  const busy = pending > 0;
  async function act(task, clear = true) {
    setPending((n) => n + 1);
    if (clear) {
      setError("");
      setMessage("");
    }
    try {
      await task();
    } catch (err) {
      setError(err.message);
    } finally {
      setPending((n) => n - 1);
    }
  }
  const changed = (text) => {
    setMessage(text);
    setRevision((n) => n + 1);
  };
  useEffect(() => {
    const navigate = () => {
      setRoute(window.location.hash.slice(1) || "library");
      setError("");
      setMessage("");
    };
    window.addEventListener("hashchange", navigate);
    return () => window.removeEventListener("hashchange", navigate);
  }, []);
  useEffect(() => {
    act(async () => setProjects(await api("/projects")), false);
  }, [revision]);
  const assetMatch = /^asset\/(\d+)$/.exec(route);
  return (
    <main>
      <header className="studio-header">
        <h1>
          image studio
          <span className="studio-dot" aria-hidden="true">
            .
          </span>
        </h1>
        <nav aria-label="Workspace">
          <a
            href="#library"
            aria-current={route === "library" ? "page" : undefined}
          >
            Asset library
          </a>
          <a
            href="#projects"
            aria-current={route === "projects" ? "page" : undefined}
          >
            Projects
          </a>
        </nav>
      </header>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      {message && (
        <div className="notice" role="status">
          {message}
        </div>
      )}
      {busy && (
        <p className="progress" role="status">
          Working…
        </p>
      )}
      {route === "projects" ? (
        <section>
          <h2>Projects</h2>
          <p className="intro">
            Give each project a name and shared creative direction.
          </p>
          <ProjectForm act={act} changed={changed} busy={busy} />
          {projects.map((p) => (
            <ProjectForm
              key={p.id}
              project={p}
              act={act}
              changed={changed}
              busy={busy}
            />
          ))}
        </section>
      ) : assetMatch ? (
        <AssetPage
          key={assetMatch[1]}
          id={assetMatch[1]}
          projects={projects}
          act={act}
          changed={changed}
          busy={busy}
        />
      ) : (
        <Library
          projects={projects}
          act={act}
          revision={revision}
          busy={busy}
        />
      )}
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
