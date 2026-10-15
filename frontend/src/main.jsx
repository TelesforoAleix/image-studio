import { performAction } from "./Actions";
import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
import { flushNavigation } from "./navigation";
import { api } from "./api";
import { OutputPage } from "./Feedback";
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
  async function act(task, action = true) {
    const hash = window.location.hash;
    return performAction(
      async () => {
        await task();
        if (action && window.location.hash !== hash)
          setMessage((current) => current || "Done.");
      },
      action ? undefined : (err) => setError(err.message),
    );
  }
  useEffect(() => {
    if (!message) return;
    const timer = setTimeout(() => setMessage(""), 4000);
    return () => clearTimeout(timer);
  }, [message]);
  const changed = (text) => {
    setMessage(text);
    setRevision((n) => n + 1);
  };
  const displayedRoute = useRef(route);
  displayedRoute.current = route;
  useEffect(() => {
    let navigation = 0;
    const navigate = async () => {
      const next = window.location.hash.slice(1) || "assets";
      const request = ++navigation;
      try {
        await flushNavigation();
        if (request !== navigation) return;
        setRoute(next);
        setError("");
      } catch {
        if (request === navigation)
          window.history.replaceState(null, "", `#${displayedRoute.current}`);
      }
    };
    window.addEventListener("hashchange", navigate);
    return () => window.removeEventListener("hashchange", navigate);
  }, []);
  useEffect(() => {
    act(async () => setProjects(await api("/projects")), false);
  }, [revision]);
  const projectMatch = /^project\/(\d+)$/.exec(route);
  const compositionMatch =
    /^composition\/(\d+)(?:\/frame\/(\d+)(?:\/(setup|generate|history))?)?$/.exec(
      route,
    );
  const frameMatch = /^frame\/(\d+)$/.exec(route);
  useEffect(() => {
    if (compositionMatch?.[3])
      window.location.replace(
        `#composition/${compositionMatch[1]}/frame/${compositionMatch[2]}`,
      );
    if (route === "library") window.location.replace("#assets");
    if (frameMatch)
      act(async () => {
        const frame = await api(`/variants/${frameMatch[1]}`);
        if (frame.deleted_at) throw new Error("This frame has been deleted.");
        window.location.replace(
          `#composition/${frame.composition_id}/frame/${frame.id}`,
        );
      }, false);
  }, [route]);
  const assetFilter =
    new URLSearchParams(route.split("?")[1] || "").get("used_by_project") || "";
  const outputMatch = /^output\/(\d+)\/(\d+)$/.exec(route);
  const assetMatch = /^asset\/(\d+)$/.exec(route);
  return (
    <main className={compositionMatch ? "workspace-main" : undefined}>
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
        <div className="notice toast" role="status">
          {message}
        </div>
      )}
      {outputMatch ? (
        <OutputPage
          key={route}
          id={outputMatch[1]}
          output={Number(outputMatch[2])}
          {...{ act }}
        />
      ) : route === "storage" ? (
        <Storage act={act} />
      ) : route === "projects" ? (
        <section>
          <h2>Projects</h2>
          <p className="intro">
            Give each project a name and shared creative direction.
          </p>
          <ProjectForm act={act} changed={changed} />
          {projects.map((p) => (
            <p key={p.id}>
              <a href={`#project/${p.id}`}>{p.name}</a>
            </p>
          ))}
        </section>
      ) : route === "compositions" ? (
        <Compositions {...{ projects, act }} />
      ) : projectMatch ? (
        <ProjectPage
          key={projectMatch[1]}
          projects={projects}
          id={projectMatch[1]}
          act={act}
          changed={changed}
        />
      ) : compositionMatch ? (
        <CompositionPage
          key={compositionMatch[1]}
          id={compositionMatch[1]}
          frameId={compositionMatch[2]}
          tab={compositionMatch[3]}
          projects={projects}
          act={act}
        />
      ) : assetMatch ? (
        <AssetPage
          key={assetMatch[1]}
          id={assetMatch[1]}
          projects={projects}
          act={act}
          changed={changed}
        />
      ) : (
        <Library
          projects={projects}
          projectFilter={assetFilter}
          act={act}
          revision={revision}
        />
      )}
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
