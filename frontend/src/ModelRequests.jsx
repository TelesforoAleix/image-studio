import {
  ActionButton,
  ActionInput,
  ActionSelect,
  ActionTextarea,
} from "./Actions";
import React, { useEffect, useState } from "react";
import { api } from "./api";
import { ModelCost } from "./ModelCost";

export function formats(info) {
  return info.sizes
    ? [...new Set(info.sizes.map((s) => s.aspect_ratio))]
    : Object.keys(info.aspect_ratios?.values || {}).map((k) =>
        Array.isArray(info.aspect_ratios.values)
          ? info.aspect_ratios.values[k]
          : k,
      );
}
function prices(info, format) {
  if (info.sizes)
    return Object.fromEntries(
      info.sizes
        .filter((s) => s.aspect_ratio === format && s.price != null)
        .map((s) => [s.value, s.price]),
    );
  const spec = info.qualities || info.resolutions;
  return Object.fromEntries(
    Object.entries(info.price_per_image || {}).filter(
      ([k]) => !spec || spec.values.includes(k),
    ),
  );
}
export function defaults(info, format) {
  const costs = prices(info, format);
  return {
    format,
    quality: Object.keys(costs).sort((a, b) => costs[a] - costs[b])[0],
    advanced: Object.fromEntries(
      (info.advanced || []).map((s) => [s.name, s.default]),
    ),
  };
}
export function ModelRequests({
  models,
  choices,
  setChoices,
  format,
  setFormat,
  content,
  references,
  onPreview,
  revision,
  limit = 3,
  workspace = false,
}) {
  const [panels, setPanels] = useState([]);
  const [sheet, setSheet] = useState(false);
  const [error, setError] = useState("");
  const [spend, setSpend] = useState(null);
  useEffect(() => {
    api("/spend")
      .then(setSpend)
      .catch((e) => setError(e.message));
  }, [revision]);
  useEffect(() => {
    let active = true;
    onPreview(null);
    setError("");
    const timer = setTimeout(async () => {
      if (!choices.length || !content) {
        if (active) setPanels([]);
        return;
      }
      try {
        const result = await api("/render", "POST", {
          content,
          references,
          models: choices,
          format,
        });
        if (active) {
          setPanels(result);
          onPreview(result);
        }
      } catch (e) {
        if (active) {
          setPanels([]);
          setError(e.message);
        }
      }
    }, 200);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [models, choices, format, content, references]);
  const chosen = models.filter((m) =>
    choices.some((c) => c.model === m.model_name),
  );
  const ratios = chosen.length
    ? formats(chosen[0].model_info).filter((r) =>
        chosen.every((m) => formats(m.model_info).includes(r)),
      )
    : [...new Set(models.flatMap((m) => formats(m.model_info)))];
  const change = (name, values) =>
    setChoices(
      choices.map((c) => (c.model === name ? { ...c, ...values } : c)),
    );
  const settingsPanel = (c, info, settings, price) => (
    <>
      {" "}
      <label>
        Outputs
        <ActionSelect
          value={c.count}
          onChange={(e) => change(c.model, { count: Number(e.target.value) })}
        >
          {[1, 2, 3, 4].map((n) => (
            <option key={n}>{n}</option>
          ))}
        </ActionSelect>
      </label>
      <label>
        {info.resolutions
          ? "Resolution"
          : info.sizes
            ? "Size / resolution"
            : "Quality"}
        <ActionSelect
          value={settings.quality}
          onChange={(e) =>
            change(c.model, {
              settings: { ...settings, quality: e.target.value },
            })
          }
        >
          {Object.entries(prices(info, format)).map(([v, p]) => (
            <option key={v} value={v}>
              {v} · ${p}
            </option>
          ))}
        </ActionSelect>
      </label>
      <p>
        ${price} per image
        {info.price_per_reference != null &&
          ` + $${info.price_per_reference} per reference`}
        {info.price_estimated && " (estimated)"}
      </p>
      <details>
        <summary>Advanced</summary>
        {(info.advanced || []).map((s) => (
          <label key={s.name}>
            {s.name}
            {s.values ? (
              <ActionSelect
                value={settings.advanced?.[s.name]}
                onChange={(e) =>
                  change(c.model, {
                    settings: {
                      ...settings,
                      advanced: {
                        ...settings.advanced,
                        [s.name]: e.target.value,
                      },
                    },
                  })
                }
              >
                {s.values.map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </ActionSelect>
            ) : (
              <ActionInput
                type="number"
                min={s.range[0]}
                max={s.range[1]}
                step="1"
                value={settings.advanced?.[s.name]}
                onChange={(e) =>
                  change(c.model, {
                    settings: {
                      ...settings,
                      advanced: {
                        ...settings.advanced,
                        [s.name]: Number(e.target.value),
                      },
                    },
                  })
                }
              />
            )}
          </label>
        ))}
      </details>
      {workspace && (
        <ActionButton
          type="button"
          onClick={() => setChoices(choices.filter((x) => x.model !== c.model))}
        >
          Remove
        </ActionButton>
      )}
    </>
  );
  const promptPanel = (c, info, panel) => (
    <>
      {" "}
      <h4>Prompt to send</h4>
      {c.prompt !== undefined ? (
        <ActionTextarea
          aria-label={`Prompt for ${info.display_name}`}
          rows="12"
          value={c.prompt}
          onChange={(e) => change(c.model, { prompt: e.target.value })}
        />
      ) : (
        <pre>{panel?.rendered_prompt || "Preparing preview…"}</pre>
      )}
      <div className="actions">
        <ActionButton
          className="plain"
          type="button"
          disabled={!panel}
          onClick={() => change(c.model, { prompt: panel.rendered_prompt })}
        >
          Edit
        </ActionButton>
        <ActionButton
          className="plain"
          type="button"
          onClick={() =>
            setChoices(
              choices.map((x) => {
                if (x.model !== c.model) return x;
                const { prompt, ...rest } = x;
                return rest;
              }),
            )
          }
        >
          Reset
        </ActionButton>
      </div>
      <div className="reference-toggles">
        {panel?.references.map((r, i) => (
          <figure key={i}>
            <img
              src={`/api/files/${r.hash}`}
              alt={`Image ${i + 1}: ${r.asset_name}`}
            />
            <figcaption>
              Image {i + 1}: {r.asset_name} · {r.role}
            </figcaption>
          </figure>
        ))}
      </div>
    </>
  );
  return (
    <>
      <label>
        Format
        <ActionSelect
          aria-label="Format"
          value={format}
          onChange={(e) => {
            setFormat(e.target.value);
            setChoices(
              choices.map((c) => ({
                ...c,
                settings: (() => {
                  const info = models.find(
                    (m) => m.model_name === c.model,
                  )?.model_info;
                  if (!info) return c.settings;
                  const next = defaults(info, e.target.value);
                  return {
                    ...next,
                    advanced: c.settings?.advanced || next.advanced,
                    quality:
                      c.settings?.quality in prices(info, e.target.value)
                        ? c.settings.quality
                        : next.quality,
                  };
                })(),
              })),
            );
          }}
        >
          {ratios.map((r) => (
            <option key={r}>{r}</option>
          ))}
        </ActionSelect>
      </label>
      <details
        onKeyDown={(e) => {
          if (workspace && e.key === "Escape") {
            e.currentTarget.open = false;
            e.currentTarget.querySelector("summary").focus();
          }
        }}
        className={workspace ? "model-picker" : "model-picker-inline"}
        open={workspace ? undefined : true}
      >
        <summary>{workspace ? "+ model" : "Models"}</summary>
        <fieldset>
          <legend>
            {limit === 1 ? "Choose a model" : "Compare one to three models"}
          </legend>
          {models.map((m) => {
            const c = choices.find((c) => c.model === m.model_name);
            const supports = formats(m.model_info).includes(format);
            return (
              <div className="model-option" key={m.model_name}>
                <label>
                  <span>
                    <ActionInput
                      type="checkbox"
                      checked={!!c}
                      disabled={!c && (!supports || choices.length >= limit)}
                      onChange={(e) =>
                        setChoices(
                          e.target.checked
                            ? [
                                ...choices,
                                {
                                  model: m.model_name,
                                  count: 1,
                                  settings: defaults(m.model_info, format),
                                },
                              ]
                            : choices.filter((x) => x.model !== m.model_name),
                        )
                      }
                    />
                    {m.model_info.display_name}
                  </span>
                </label>
                <ModelCost info={m.model_info} />
                {workspace && (
                  <p>
                    Accepts {m.model_info.max_references} references ·{" "}
                    {m.model_info.seconds_per_image == null
                      ? "Time unknown"
                      : `About ${m.model_info.seconds_per_image} seconds per image`}
                  </p>
                )}
                {!supports && <p>Does not support {format}</p>}
                {m.model_info.placeholder && (
                  <span className="badge">Placeholder</span>
                )}
              </div>
            );
          })}
          {choices
            .filter((c) => !models.some((m) => m.model_name === c.model))
            .map((c) => (
              <p className="error" key={c.model}>
                {c.model} is no longer available.{" "}
                <ActionButton
                  className="plain"
                  type="button"
                  onClick={() =>
                    setChoices(choices.filter((x) => x.model !== c.model))
                  }
                >
                  Remove model
                </ActionButton>
              </p>
            ))}
        </fieldset>
      </details>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className={workspace ? "model-chips" : "request-panels"}>
        {choices.map((c) => {
          const info = models.find((m) => m.model_name === c.model)?.model_info;
          if (!info) return null;
          const settings = c.settings || defaults(info, format);
          const panel = panels.find((p) => p.model === c.model);
          const price = prices(info, format)[settings.quality];
          return (
            <section
              className={
                workspace ? "model-chip-container" : "panel model-column"
              }
              key={c.model}
            >
              {!workspace && <h3>{info.display_name}</h3>}
              {workspace ? (
                <details
                  className="model-chip"
                  onKeyDown={(e) => {
                    if (e.key === "Escape") {
                      e.currentTarget.open = false;
                      e.currentTarget.querySelector("summary").focus();
                    }
                  }}
                >
                  <summary>
                    {info.display_name} · {c.count} outputs · {settings.quality}
                    {c.prompt !== undefined && (
                      <span className="badge">Edited prompt</span>
                    )}
                  </summary>
                  <div className="chip-popover">
                    {settingsPanel(c, info, settings, price)}
                  </div>
                </details>
              ) : (
                <>
                  {settingsPanel(c, info, settings, price)}
                  {promptPanel(c, info, panel)}
                </>
              )}
              {!workspace && panel && (
                <p>
                  Model cost: ${panel.estimated_cost.toFixed(5)}
                  {info.price_estimated && " (estimated)"}
                </p>
              )}
            </section>
          );
        })}
      </div>
      {workspace && (
        <>
          <button
            type="button"
            aria-haspopup="dialog"
            onClick={() => setSheet(true)}
          >
            View prompts ({choices.length})
          </button>
          {sheet && (
            <div
              className="prompt-sheet"
              role="dialog"
              aria-modal="false"
              aria-label="View prompts"
              onKeyDown={(e) => {
                if (e.key === "Escape") {
                  setSheet(false);
                  e.currentTarget.previousElementSibling?.focus();
                }
              }}
            >
              <div className="sheet-heading">
                <h2>Prompts as sent</h2>
                <button type="button" autoFocus onClick={() => setSheet(false)}>
                  Close prompts
                </button>
              </div>
              {choices.map((c) => {
                const info = models.find(
                  (m) => m.model_name === c.model,
                )?.model_info;
                return (
                  info && (
                    <section key={c.model}>
                      <h3>{info.display_name}</h3>
                      {promptPanel(
                        c,
                        info,
                        panels.find((p) => p.model === c.model),
                      )}
                    </section>
                  )
                );
              })}
            </div>
          )}
        </>
      )}
      <p>
        Estimated run cost:{" "}
        {panels.length === choices.length && panels.length
          ? `$${panels.reduce((s, p) => s + p.estimated_cost, 0).toFixed(5)}${chosen.some((m) => m.model_info.price_estimated) ? " (estimated)" : ""}`
          : "Choose models and valid settings"}
      </p>
      <p>
        This month's estimated spend (UTC):{" "}
        {spend ? `$${spend.estimated_spend.toFixed(5)}` : "Loading…"} · budget:
        $20 a month, enforced by the platform
      </p>
    </>
  );
}
