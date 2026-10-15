import React, { useEffect, useRef } from "react";

export function Sheet({ title, onClose, children }) {
  const dialog = useRef(null);
  useEffect(() => {
    const previous = document.activeElement;
    dialog.current.showModal();
    return () => {
      previous?.focus();
    };
  }, []);
  return (
    <dialog
      ref={dialog}
      className="form-sheet"
      aria-label={title}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
    >
      <div className="library-header">
        <h2>{title}</h2>
        <button type="button" onClick={onClose}>
          Cancel
        </button>
      </div>
      {children}
    </dialog>
  );
}
