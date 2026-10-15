import React, { useEffect, useState } from "react";

export const hasActive = (generations) =>
  generations.some((g) => g.state === "waiting" || g.state === "running");

export function GenerationProgress({ generation: g }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (g.state !== "running") return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [g.state, g.started_at]);
  const elapsed = g.started_at
    ? Math.max(0, Math.floor((now - Date.parse(g.started_at)) / 1000))
    : null;
  const estimate = g.model_info?.seconds_per_image;
  // A rough profile estimate for unfinished outputs, not a service deadline.
  const remaining =
    estimate > 0
      ? Math.ceil(estimate * Math.max(0, g.count - g.outputs.length))
      : null;
  return (
    <span>
      {g.state === "waiting" ? "Waiting for the image service" : g.state}
      {" · "}
      {g.outputs.length}/{g.count}
      {g.state === "running" && elapsed !== null && (
        <>
          {" · "}
          {elapsed} s elapsed
          {remaining !== null && ` · about ${remaining} s left`}
        </>
      )}
    </span>
  );
}
