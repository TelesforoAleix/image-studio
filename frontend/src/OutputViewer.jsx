import React, {
  createContext,
  useContext,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { api } from "./api";
import { Feedback } from "./Feedback";
import { ActionButton } from "./Actions";

const ViewerContext = createContext(null);
export const outputKey = (id, output) => `${id}.${output}`;
export function outputHref(id, output) {
  return `#${location.hash.slice(1).split("?")[0]}?output=${outputKey(id, output)}`;
}
export function ViewerProvider({ children }) {
  const [source, setSource] = useState(null);
  const [picks, setPicks] = useState([]);
  return (
    <ViewerContext.Provider value={{ source, setSource, picks, setPicks }}>
      {children}
    </ViewerContext.Provider>
  );
}
export function useViewerSource(data, dependencies) {
  const { setSource } = useContext(ViewerContext);
  const latest = useRef(data);
  latest.current = data;
  useEffect(() => {
    const source = { get: () => latest.current };
    setSource(source);
    return () => setSource((current) => (current === source ? null : current));
  }, dependencies);
}
export function ComparePick({ generation, output }) {
  const { source, picks: selected, setPicks } = useContext(ViewerContext);
  const available = (source?.get().runs || []).flatMap(orderedOutputs);
  const picks = selected.filter((key) => available.some((o) => o.key === key));
  const key = outputKey(generation.id, output);
  return (
    <label className="compare-pick">
      <input
        type="checkbox"
        checked={picks.includes(key)}
        disabled={!picks.includes(key) && picks.length >= 3}
        onChange={(e) =>
          setPicks(
            e.target.checked ? [...picks, key] : picks.filter((p) => p !== key),
          )
        }
      />{" "}
      Compare {generation.model_info.display_name}, output {output + 1}
    </label>
  );
}
// Match the results' model columns, with each model's retry attempts below it.
export function orderedOutputs(run) {
  return run.generations
    .filter((g) => !g.retry_of)
    .flatMap((original) =>
      run.generations
        .filter((g) => g.model === original.model)
        .flatMap((g) =>
          g.outputs.map((hash, output) => ({
            g,
            output: g.raw ? g.imageIds[output] : output,
            hash,
            key: outputKey(g.id, g.raw ? g.imageIds[output] : output),
          })),
        ),
    );
}
export function OutputViewer({ token, base, act }) {
  const { source, picks } = useContext(ViewerContext);
  const data = source?.get();
  const [fallback, setFallback] = useState(null);
  const [error, setError] = useState("");
  const [comparison, setComparison] = useState(null);
  const dialog = useRef(null);
  const feedback = useRef(null);
  const origin = useRef(document.activeElement);
  const [id, index] = token.split(".").map(Number);
  const runs = data?.runs || [];
  const all = [
    ...runs.flatMap(orderedOutputs),
    ...(data?.imageRun ? orderedOutputs(data.imageRun) : []),
  ];
  const current =
    all.find((o) => o.key === token) ||
    (fallback?.id === id && fallback.outputs[index]
      ? {
          g: fallback,
          output: index,
          hash: fallback.outputs[index],
          key: token,
        }
      : null);
  useEffect(() => {
    let active = true;
    setError("");
    if (id !== 0 && !all.some((o) => o.key === token))
      api(`/generations/${id}`)
        .then((g) => {
          if (active) {
            if (!g.outputs[index]) throw new Error("Output not found");
            setFallback(g);
          }
        })
        .catch((e) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, [token, source]);
  useEffect(() => {
    const node = dialog.current;
    node.showModal();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      node.close();
      document.body.style.overflow = overflow;
      origin.current?.focus({ preventScroll: true });
    };
  }, []);
  useLayoutEffect(() => {
    if (
      dialog.current?.open &&
      (!dialog.current.contains(document.activeElement) ||
        document.activeElement.disabled)
    )
      dialog.current
        .querySelector('.viewer-image[aria-pressed="true"]')
        ?.focus();
  }, [token]);
  const move = (key) => {
    setComparison((old) =>
      old && !old.includes(key) ? old.map((k) => (k === token ? key : k)) : old,
    );
    history.replaceState(history.state, "", `#${base}?output=${key}`);
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  };
  const close = () => {
    // Opening a suffix always creates one history entry, including old links.
    if (history.state?.outputViewer) history.back();
    else {
      history.replaceState(null, "", `#${base}`);
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    }
  };
  const runIndex = runs.findIndex((r) =>
    r.generations.some((g) => g.id === id),
  );
  const row = current?.g.raw
    ? orderedOutputs(data.imageRun)
    : runIndex < 0
      ? current
        ? [current]
        : []
      : orderedOutputs(runs[runIndex]);
  const position = row.findIndex((o) => o.key === token);
  const step = (delta) => {
    const target = row[position + delta];
    if (target) move(target.key);
  };
  const stepRun = (delta) => {
    // Runs are newest first; Up goes to the previous (older) run.
    const outputs =
      runs[runIndex + delta] && orderedOutputs(runs[runIndex + delta]);
    if (outputs?.length)
      move(outputs[Math.min(Math.max(position, 0), outputs.length - 1)].key);
  };
  const compare = () => {
    if (comparison) {
      setComparison(null);
      return;
    }
    const keys = [
      token,
      ...picks.filter((k) => k !== token && all.some((o) => o.key === k)),
    ];
    const defaults = [
      token,
      ...row.map((o) => o.key).filter((k) => k !== token),
    ];
    const next = (keys.length > 1 ? keys : defaults).slice(0, 3);
    if (next.length > 1) setComparison(next);
  };
  const escape = () => {
    if (feedback.current?.cancel()) return;
    if (comparison) setComparison(null);
    else close();
  };
  const shown = comparison
    ? comparison
        .map(
          (k) =>
            all.find((o) => o.key === k) ||
            (current?.key === k ? current : null),
        )
        .filter(Boolean)
    : current
      ? [current]
      : [];
  const saved = (next) => {
    data?.saveFeedback?.(id, index, next);
    setFallback((old) =>
      old?.id === id
        ? {
            ...old,
            feedback: old.outputs.map((_, i) =>
              i === index ? next : old.feedback?.[i],
            ),
          }
        : old,
    );
  };
  return createPortal(
    <dialog
      ref={dialog}
      className="output-viewer"
      aria-label="Output viewer"
      aria-modal="true"
      onCancel={(e) => {
        e.preventDefault();
        escape();
      }}
      onKeyDown={(e) => {
        e.stopPropagation();
        if (e.key === "Tab") {
          const controls = [
            ...dialog.current.querySelectorAll(
              "button:not(:disabled), a[href], input:not(:disabled), textarea:not(:disabled), select:not(:disabled), summary",
            ),
          ].filter((node) => node.getClientRects().length);
          const first = controls[0],
            last = controls.at(-1);
          if (e.shiftKey && document.activeElement === first) {
            e.preventDefault();
            last?.focus();
          } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault();
            first?.focus();
          }
          return;
        }
        if (e.key === "Escape") {
          e.preventDefault();
          escape();
          return;
        }
        if (
          e.altKey ||
          e.ctrlKey ||
          e.metaKey ||
          e.shiftKey ||
          e.repeat ||
          e.target.matches("input, textarea, select, [contenteditable=true]")
        )
          return;
        // Native form submission and disclosure/button activation keep their keys.
        if (
          e.key === "Enter" &&
          (e.target.closest("form") || e.target.matches("summary"))
        )
          return;
        const actions = {
          ArrowLeft: () => step(-1),
          ArrowRight: () => step(1),
          ArrowUp: () => stepRun(1),
          ArrowDown: () => stepRun(-1),
          g: () => feedback.current?.verdict("good"),
          n: () => feedback.current?.verdict("not_good"),
          f: () => dialog.current.querySelector("[data-final]")?.click(),
          Enter: () => feedback.current?.open(),
          c: compare,
        };
        const action =
          actions[e.key.length === 1 ? e.key.toLowerCase() : e.key];
        if (action) {
          e.preventDefault();
          action();
        }
      }}
    >
      <header className="viewer-toolbar">
        <strong>{comparison ? "Compare outputs" : "Output viewer"}</strong>
        <button onClick={() => step(-1)} disabled={position <= 0}>
          ← Previous output
        </button>
        <button onClick={() => step(1)} disabled={position >= row.length - 1}>
          Next output →
        </button>
        <button
          onClick={() => stepRun(1)}
          disabled={runIndex < 0 || runIndex >= runs.length - 1}
        >
          ↑ Previous run
        </button>
        <button onClick={() => stepRun(-1)} disabled={runIndex <= 0}>
          ↓ Next run
        </button>
        <button
          disabled={
            !comparison &&
            row.length < 2 &&
            !picks.some((k) => k !== token && all.some((o) => o.key === k))
          }
          aria-pressed={!!comparison}
          onClick={compare}
        >
          Compare <kbd>C</kbd>
        </button>
        <button onClick={escape}>
          {comparison ? "Single view" : "Close"} <kbd>Esc</kbd>
        </button>
      </header>
      {error && <p role="alert">{error}</p>}
      {!current && !error && <p role="status">Loading output…</p>}
      <div
        className="viewer-images"
        style={{ "--viewer-columns": shown.length || 1 }}
      >
        {shown.map((o) => (
          <button
            key={o.key}
            className="viewer-image"
            aria-label={`Focus ${o.g.model_info.display_name}, output ${o.output + 1}`}
            aria-pressed={o.key === token}
            onFocus={() => {
              if (o.key !== token) move(o.key);
            }}
            onClick={() => move(o.key)}
          >
            <img
              src={`/api/files/${o.hash}`}
              alt={`${o.g.model_info.display_name}, output ${o.output + 1}`}
            />
          </button>
        ))}
      </div>
      {current && (
        <footer className="viewer-footer">
          <div className="viewer-metadata" aria-live="polite">
            <strong>
              {current.g.raw
                ? "Original image"
                : `${current.g.model_info.display_name} · Output ${index + 1}`}
            </strong>
            {!current.g.raw && (
              <>
                <span>
                  {new Date(current.g.created_at).toLocaleString()}
                  {current.g.finished_at && current.g.started_at
                    ? ` · ${Math.max(0, Math.round((Date.parse(current.g.finished_at) - Date.parse(current.g.started_at)) / 1000))} s`
                    : ""}
                </span>
                <span>
                  {current.g.settings?.format || "Format unknown"} ·{" "}
                  {current.g.settings?.quality || "Quality unknown"}
                </span>
                <span>
                  Estimated cost:{" "}
                  {current.g.estimated_cost == null
                    ? "Unavailable"
                    : `$${current.g.estimated_cost}`}
                </span>
                <span>
                  {current.g.feedback?.[index]?.verdict === "good"
                    ? "Good"
                    : current.g.feedback?.[index]?.verdict === "not_good"
                      ? "Not good"
                      : "Unrated"}
                </span>
              </>
            )}
          </div>
          {!current.g.raw && data?.lineage?.(current.hash) && (
            <div className="lineage">
              <small>
                From originals · generation{" "}
                {data.lineage(current.hash).generation_id}
              </small>
              {data.lineage(current.hash).originals.map((ref, i) => (
                <a
                  key={i}
                  href={`/api/files/${ref.hash}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  <img
                    src={`/api/files/${ref.hash}`}
                    alt={`Original ${i + 1}`}
                  />
                </a>
              ))}
            </div>
          )}
          {!current.g.raw && (
            <div className="viewer-actions">
              <Feedback
                key={token}
                ref={feedback}
                shortcuts
                primary
                generation={current.g}
                output={index}
                act={act}
                saved={saved}
              />
              {data?.choose && current.g.state === "done" && (
                <ActionButton
                  data-final
                  aria-pressed={
                    data.final?.generation_id === id &&
                    data.final?.output === index
                  }
                  onClick={() => data.choose(current.g, index)}
                >
                  {data.final?.generation_id === id &&
                  data.final?.output === index
                    ? "Final"
                    : "Mark final"}{" "}
                  <kbd>F</kbd>
                </ActionButton>
              )}
              <details>
                <summary>Technical details</summary>
                <p>Prompt as sent</p>
                <pre>{current.g.prompt}</pre>
                <p>Request fields</p>
                <pre>{JSON.stringify(current.g.request_fields, null, 2)}</pre>
                <p>Snapshot</p>
                <pre>{JSON.stringify(current.g, null, 2)}</pre>
              </details>
            </div>
          )}
        </footer>
      )}
    </dialog>,
    document.body,
  );
}
