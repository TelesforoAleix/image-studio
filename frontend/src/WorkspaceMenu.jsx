import React, { useEffect, useRef, useState } from "react";

// Native buttons/links retain click semantics; roving focus adds menu keys.
export function WorkspaceMenu({ label, icon, children, above = false }) {
  const [open, setOpen] = useState(false);
  const root = useRef(null);
  const trigger = useRef(null);
  useEffect(() => {
    if (!open) return;
    const outside = (e) => {
      if (!root.current?.contains(e.target)) setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);
  const focus = (last = false) =>
    requestAnimationFrame(() => {
      const items = root.current?.querySelectorAll(
        '[role="menuitem"]:not(:disabled)',
      );
      items?.[last ? items.length - 1 : 0]?.focus();
    });
  return (
    <div
      className="workspace-menu"
      ref={root}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) setOpen(false);
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.preventDefault();
          setOpen(false);
          trigger.current.focus();
        }
        if (["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) {
          e.preventDefault();
          if (!open) {
            setOpen(true);
            focus(e.key === "ArrowUp");
            return;
          }
          const items = [
            ...root.current.querySelectorAll(
              '[role="menuitem"]:not(:disabled)',
            ),
          ];
          const i = items.indexOf(document.activeElement);
          items[
            e.key === "Home"
              ? 0
              : e.key === "End"
                ? items.length - 1
                : (i + (e.key === "ArrowUp" ? -1 : 1) + items.length) %
                  items.length
          ]?.focus();
        }
      }}
    >
      <button
        type="button"
        ref={trigger}
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => {
          setOpen(!open);
          if (!open) focus();
        }}
      >
        {icon || label}
      </button>
      {open && (
        <div
          className="menu-panel"
          role="menu"
          aria-label={label}
          style={{
            position: "fixed",
            top: above
              ? "auto"
              : trigger.current?.getBoundingClientRect().bottom + 8,
            bottom: above
              ? window.innerHeight -
                trigger.current?.getBoundingClientRect().top +
                8
              : "auto",
            left: Math.min(
              trigger.current?.getBoundingClientRect().left,
              window.innerWidth - 316,
            ),
            right: "auto",
          }}
          onClick={(e) => {
            if (e.target.closest('[role="menuitem"]') && !e.target.disabled) {
              setOpen(false);
              trigger.current.focus();
            }
          }}
        >
          {children}
        </div>
      )}
    </div>
  );
}
