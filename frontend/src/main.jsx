import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
import { api } from "./api";
import { Storage } from "./Storage";
import { Library } from "./Library";
import { AssetPage } from "./AssetPage";
import { ProjectForm } from "./ProjectForm";
import { CompositionPage } from "./Composition";
import { ProjectPage, Compositions } from "./Compositions";

function App() {
  const [route, setRoute] = useState(window.location.hash.slice(1) || "assets");
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
      setRoute(window.location.hash.slice(1) || "assets");
      setError("");
      setMessage("");
    };
    window.addEventListener("hashchange", navigate);
    return () => window.removeEventListener("hashchange", navigate);
  }, []);
  useEffect(() => {
    act(async () => setProjects(await api("/projects")), false);
  }, [revision]);
  const projectMatch = /^project\/(\d+)$/.exec(route);
  const compositionMatch =
    /^composition\/(\d+)(?:\/frame\/(\d+)\/(setup|generate|history))?$/.exec(
      route,
    );
  const frameMatch = /^frame\/(\d+)$/.exec(route);
  useEffect(() => {
    if (route === "library") window.location.replace("#assets");
    if (frameMatch)
      act(async () => {
        const frame = await api(`/variants/${frameMatch[1]}`);
        if (frame.deleted_at) throw new Error("This frame has been deleted.");
        window.location.replace(
          `#composition/${frame.composition_id}/frame/${frame.id}/setup`,
        );
      }, false);
  }, [route]);
  const assetFilter =
    new URLSearchParams(route.split("?")[1] || "").get("used_by_project") || "";
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
            href="#assets"
            aria-current={
              route.startsWith("assets") || assetMatch ? "page" : undefined
            }
          >
            Assets
          </a>
          <a
            href="#compositions"
            aria-current={
              route === "compositions" || compositionMatch || frameMatch
                ? "page"
                : undefined
            }
          >
            Compositions
          </a>
          <a
            href="#projects"
            aria-current={route === "projects" ? "page" : undefined}
          >
            Projects
          </a>
          <a
            className="secondary-link"
            href="#storage"
            aria-current={route === "storage" ? "page" : undefined}
          >
            Storage
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
      {route === "storage" ? (
        <Storage act={act} busy={busy} />
      ) : route === "projects" ? (
        <section>
          <h2>Projects</h2>
          <p className="intro">
            Give each project a name and shared creative direction.
          </p>
          <ProjectForm act={act} changed={changed} busy={busy} />
          {projects.map((p) => (
            <p key={p.id}>
              <a href={`#project/${p.id}`}>{p.name}</a>
            </p>
          ))}
        </section>
      ) : route === "compositions" ? (
        <Compositions {...{ projects, act, busy }} />
      ) : projectMatch ? (
        <ProjectPage
          key={projectMatch[1]}
          projects={projects}
          id={projectMatch[1]}
          act={act}
          changed={changed}
          busy={busy}
        />
      ) : compositionMatch ? (
        <CompositionPage
          key={compositionMatch[1]}
          id={compositionMatch[1]}
          frameId={compositionMatch[2]}
          tab={compositionMatch[3]}
          projects={projects}
          act={act}
          busy={busy}
        />
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
          projectFilter={assetFilter}
          act={act}
          revision={revision}
          busy={busy}
        />
      )}
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
