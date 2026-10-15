import { useEffect, useRef, useState } from "react";
import { guardNavigation } from "./navigation";
import { assetValues } from "./AssetFields";
import { api } from "./api";

export function useAutosave(composition, frame, setComp, asset = false) {
  const initial = asset
    ? assetValues(composition)
    : {
        name: composition.name,
        brief: composition.brief,
        frameName: frame.name,
        instructions: frame.instructions,
      };
  const [value, setValue] = useState(initial);
  const [status, setStatus] = useState({});
  const current = useRef(initial);
  const saved = useRef(initial);
  const chain = useRef(Promise.resolve());
  const timer = useRef(null);
  const mounted = useRef(true);
  const flush = () => {
    clearTimeout(timer.current);
    const task = async () => {
      const snapshot = { ...current.current };
      const dirty = Object.keys(snapshot).filter(
        (key) => snapshot[key] !== saved.current[key],
      );
      if (!dirty.length) return;
      const comp = {},
        variant = {};
      for (const key of dirty) {
        if (!asset && (key === "frameName" || key === "instructions"))
          variant[key === "frameName" ? "name" : key] = snapshot[key];
        else comp[key] = snapshot[key];
      }
      try {
        if (Object.keys(comp).length)
          await api(
            `/${asset ? "assets" : "compositions"}/${composition.id}`,
            "PATCH",
            comp,
          );
        if (Object.keys(variant).length)
          await api(`/variants/${frame.id}`, "PATCH", variant);
        for (const key of dirty) saved.current[key] = snapshot[key];
        if (mounted.current)
          setComp((old) => ({
            ...old,
            ...comp,
            ...(asset
              ? {}
              : {
                  variants: old.variants.map((v) =>
                    v.id === frame.id ? { ...v, ...variant } : v,
                  ),
                }),
          }));
        if (mounted.current)
          setStatus((old) => ({
            ...old,
            ...Object.fromEntries(
              dirty.map((key) => [
                key,
                current.current[key] === snapshot[key] ? "Saved" : "Saving…",
              ]),
            ),
          }));
        if (
          Object.keys(current.current).some(
            (key) => current.current[key] !== saved.current[key],
          )
        )
          await task();
      } catch (e) {
        if (mounted.current)
          setStatus((old) => ({
            ...old,
            ...Object.fromEntries(dirty.map((key) => [key, e.message])),
          }));
        throw e;
      }
    };
    chain.current = chain.current.catch(() => {}).then(task);
    return chain.current;
  };
  const change = (key, next) => {
    current.current = { ...current.current, [key]: next };
    setValue(current.current);
    setStatus((old) => ({ ...old, [key]: "Saving…" }));
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      flush().catch(() => {});
    }, 450);
  };
  const latestFlush = useRef(flush);
  latestFlush.current = flush;
  useEffect(() => {
    const leave = (e) => {
      const a = e.target.closest?.("a");
      if (
        !a ||
        a.hasAttribute("data-output") ||
        a.target === "_blank" ||
        e.metaKey ||
        e.ctrlKey ||
        e.shiftKey ||
        e.altKey ||
        e.button !== 0
      )
        return;
      const url = new URL(a.href);
      if (
        url.origin !== location.origin ||
        !url.hash ||
        url.hash === location.hash
      )
        return;
      e.preventDefault();
      latestFlush
        .current()
        .then(() => {
          location.hash = url.hash;
        })
        .catch(() => {});
    };
    // keepalive allows final PATCH requests to finish on a document unload.
    const unload = () => {
      const v = current.current,
        s = saved.current;
      const comp = {},
        variant = {};
      for (const key of asset ? Object.keys(v) : ["name", "brief"])
        if (v[key] !== s[key]) comp[key] = v[key];
      for (const key of asset ? [] : ["frameName", "instructions"])
        if (v[key] !== s[key])
          variant[key === "frameName" ? "name" : key] = v[key];
      for (const [path, body] of [
        [`/${asset ? "assets" : "compositions"}/${composition.id}`, comp],
        [`/variants/${frame.id}`, variant],
      ])
        if (Object.keys(body).length)
          fetch(`/api${path}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
            keepalive: true,
          });
    };
    const removeGuard = guardNavigation(() => latestFlush.current());
    document.addEventListener("click", leave, true);
    window.addEventListener("pagehide", unload);
    return () => {
      mounted.current = false;
      removeGuard();
      document.removeEventListener("click", leave, true);
      window.removeEventListener("pagehide", unload);
      latestFlush.current().catch(() => {});
    };
  }, []);
  return { value, change, status, flush };
}
