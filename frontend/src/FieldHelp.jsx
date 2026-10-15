import React, { useEffect, useId, useState } from "react";

export const guidance = {
  creative:
    "How every image in this project should look and feel: medium, mood, palette, light, era. It applies to all the project's compositions. Example: Warm editorial interiors, soft window light, muted earth tones.",
  single:
    "What this image shows and how it should feel: who or what is in it, where, what is happening, the framing. Refer to assets by their roles. Example: The model reads in an armchair at dusk; the lamp glows on the side table; medium shot at eye level.",
  storyboard:
    "The story as a whole: the setting, the look, and what must stay the same in every frame. Each frame then says only what happens in it. Example: A small living room on one evening; the model wears the same clothes throughout.",
  frame:
    "Only what is different in this frame: the action, pose and framing. Don't repeat the brief. Example: Stands up, book under the arm, looks back at the lamp; wide shot.",
  role: "How this asset takes part in the image. Examples: the model, worn on the legs, on the side table, the background.",
  style:
    "A Style asset sets the look through its description and example images. The project's style applies unless this composition picks its own.",
  description:
    "What the asset is, in plain words: shape, materials, colours, size. Example: Table lamp with a conical linen shade, brushed brass stem and a round marble base.",
  preserve:
    "The features a model must not change, even when the pose, angle or setting changes. Example: the shade's cone angle and linen texture; the thin brass stem; the marble's veining.",
};

export function FieldHelp({ label, help }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({});
  useEffect(() => {
    if (!open) return;
    const close = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        setOpen(false);
      }
    };
    document.addEventListener("keydown", close, true);
    return () => document.removeEventListener("keydown", close, true);
  }, [open]);
  const show = (event) => {
    const rect = event.currentTarget.getBoundingClientRect();
    setPosition({
      left: Math.max(8, Math.min(rect.left, window.innerWidth - 304)),
      top: rect.bottom,
    });
    setOpen(true);
  };
  return (
    <span
      className="field-help"
      onMouseEnter={show}
      onMouseLeave={(event) => {
        if (!event.currentTarget.contains(document.activeElement))
          setOpen(false);
      }}
    >
      <button
        type="button"
        className="help-trigger"
        aria-label={`Help: ${label}`}
        aria-describedby={open ? id : undefined}
        onFocus={show}
        onBlur={() => setOpen(false)}
        onClick={(event) => {
          event.preventDefault();
          show(event);
        }}
      >
        ⓘ
      </button>
      {open && (
        <span role="tooltip" id={id} className="field-tooltip" style={position}>
          {help}
        </span>
      )}
    </span>
  );
}
