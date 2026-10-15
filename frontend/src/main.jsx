import { performAction } from "./Actions";
import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
import { flushNavigation } from "./navigation";
import { api } from "./api";
import { OutputViewer, ViewerProvider } from "./OutputViewer";
import { Storage } from "./Storage";
import { Library } from "./Library";
import { AssetPage } from "./AssetPage";
import { ProjectForm } from "./ProjectForm";
import { CompositionPage } from "./Composition";
import { ProjectPage, Compositions } from "./Compositions";
import { Sidebar } from "./Sidebar";
import { Sheet } from "./Sheet";

function App() {
  const [route, setRoute] = useState(() => {
    const initial = location.hash.slice(1) || "studio";
    if (/\?output=\d+\.\d+$/.test(initial) && !history.state?.outputViewer) {
      history.replaceState(null, "", `#${initial.split("?")[0]}`);
      history.pushState({ outputViewer: true }, "", `#${initial}`);
    }
    return initial;
  });
  const [projects, setProjects] = useState([]);
  const [compositionProject, setCompositionProject] = useState(undefined);
  const [creatingProject, setCreatingProject] = useState(false);
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
      const next = window.location.hash.slice(1) || "studio";
      const request = ++navigation;
      try {
        if (next.split("?")[0] !== displayedRoute.current.split("?")[0])
          await flushNavigation();
        if (request !== navigation) return;
        if (
          next.includes("?output=") &&
          !displayedRoute.current.includes("?output=") &&
          next.split("?")[0] === displayedRoute.current.split("?")[0]
        )
          history.replaceState({ outputViewer: true }, "");
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
  const base = route.split("?")[0];
  useEffect(() => setCreatingProject(false), [base]);
  const requestedOutput = new URLSearchParams(route.split("?")[1] || "").get(
    "output",
  );
  const outputToken = /^\d+\.\d+$/.test(requestedOutput || "")
    ? requestedOutput
    : null;
  const projectMatch = /^studio\/project\/(\d+)$/.exec(base);
  const compositionMatch =
    /^composition\/(\d+)(?:\/frame\/(\d+)(?:\/(setup|generate|history))?)?$/.exec(
      base,
    );
  const frameMatch = /^frame\/(\d+)$/.exec(base);
  useEffect(() => {
    let active = true;
    if (compositionMatch?.[3])
      window.location.replace(
        `#composition/${compositionMatch[1]}/frame/${compositionMatch[2]}`,
      );
    const legacy = /^output\/(\d+)\/(\d+)$/.exec(base);
    if (legacy)
      act(async () => {
        const g = await api(`/generations/${legacy[1]}`);
        let parent = `asset/${g.asset_id}`;
        if (g.variant_id) {
          const frame = await api(`/variants/${g.variant_id}`);
          parent = `composition/${frame.composition_id}/frame/${frame.id}`;
        }
        if (!active) return;
        history.replaceState(null, "", `#${parent}`);
        location.hash = `${parent}?output=${legacy[1]}.${legacy[2]}`;
        history.replaceState({ outputViewer: true }, "");
      }, false);
    if (route === "library") window.location.replace("#assets");
    if (base === "projects" || base === "compositions")
      window.location.replace("#studio");
    const oldProject = /^project\/(\d+)$/.exec(base);
    const usedProject = new URLSearchParams(route.split("?")[1] || "").get(
      "used_by_project",
    );
    if (oldProject || (base === "assets" && /^\d+$/.test(usedProject || "")))
      window.location.replace(
        `#studio/project/${oldProject?.[1] || usedProject}`,
      );
    if (frameMatch)
      act(async () => {
        const frame = await api(`/variants/${frameMatch[1]}`);
        if (frame.deleted_at) throw new Error("This frame has been deleted.");
        window.location.replace(
          `#composition/${frame.composition_id}/frame/${frame.id}`,
        );
      }, false);
    return () => {
      active = false;
    };
  }, [route]);
  const outputMatch = /^output\/(\d+)\/(\d+)$/.exec(base);
  const assetMatch = /^asset\/(\d+)$/.exec(base);
  return (
    <main
      aria-hidden={outputToken ? true : undefined}
      inert={outputToken ? true : undefined}
      className={compositionMatch ? "workspace-main" : undefined}
    >
      <Sidebar
        {...{ base, projects, act, compositionProject }}
        newProject={() => setCreatingProject(true)}
      />
      <div
        className="app-content"
        aria-hidden={creatingProject || undefined}
        inert={creatingProject || undefined}
      >
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
          <p>Opening output…</p>
        ) : route === "storage" ? (
          <Storage act={act} />
        ) : base === "studio" || base === "studio/none" ? (
          <>
            <Compositions
              key={base}
              {...{ projects, act }}
              projectFilter={base === "studio/none" ? "none" : ""}
            />
            {base === "studio" && (
              <section aria-label="Projects">
                <div className="library-header">
                  <h2>Projects</h2>
                  <button onClick={() => setCreatingProject(true)}>
                    New project
                  </button>
                </div>
                <div className="project-folders">
                  {projects.map((p) => (
                    <a key={p.id} href={`#studio/project/${p.id}`}>
                      ▱ {p.name}
                    </a>
                  ))}
                </div>
                {!projects.length && <p>No projects yet.</p>}
              </section>
            )}
          </>
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
            onProject={setCompositionProject}
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
            key={base}
            type={/^assets\/([^/]+)$/.exec(base)?.[1] || ""}
            act={act}
            revision={revision}
          />
        )}
      </div>
      {creatingProject && (
        <Sheet title="New project" onClose={() => setCreatingProject(false)}>
          <ProjectForm
            {...{ act, changed }}
            onSaved={() => setCreatingProject(false)}
          />
        </Sheet>
      )}
      {outputToken && /^\d+\.\d+$/.test(outputToken) && (
        <OutputViewer token={outputToken} base={base} act={act} />
      )}
    </main>
  );
}

createRoot(document.getElementById("root")).render(
  <ViewerProvider>
    <App />
  </ViewerProvider>,
);
