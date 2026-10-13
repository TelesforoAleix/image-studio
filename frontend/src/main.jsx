import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
import { api } from "./api";
import { Library } from "./Library";
import { AssetPage } from "./AssetPage";
import { ProjectForm } from "./ProjectForm";
import { ProjectPage, CompositionPage } from "./Composition";

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
  const projectMatch = /^project\/(\d+)$/.exec(route);
  const compositionMatch = /^composition\/(\d+)$/.exec(route);
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
            Library
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
            <p key={p.id}>
              <a href={`#project/${p.id}`}>{p.name}</a>
            </p>
          ))}
        </section>
      ) : projectMatch ? (
        <ProjectPage
          key={projectMatch[1]}
          id={projectMatch[1]}
          act={act}
          changed={changed}
          busy={busy}
        />
      ) : compositionMatch ? (
        <CompositionPage
          key={compositionMatch[1]}
          id={compositionMatch[1]}
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
          act={act}
          revision={revision}
          busy={busy}
        />
      )}
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
