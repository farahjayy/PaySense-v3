"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";

type Props = {
  open: boolean;
  title: string;
  onClose: () => void;
  /** False while a save is in flight: Escape, the backdrop and the close button then do nothing. */
  dismissible?: boolean;
  children: ReactNode;
};

/**
 * A modal on the native <dialog>: focus moves in, Escape and the backdrop close it, focus returns
 * to what opened it, and the page behind is inert. Falls back to a plain open attribute where the
 * element's methods are missing (test environments).
 */
export function Dialog({ open, title, onClose, dismissible = true, children }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  // A drag that starts inside the dialog (selecting text) and ends on the backdrop is not a click on
  // the backdrop, so it must not discard what was typed.
  const pressedBackdrop = useRef(false);
  const dismiss = () => {
    if (dismissible) onClose();
  };

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      if (typeof dialog.showModal === "function") dialog.showModal();
      else dialog.setAttribute("open", "");
      // React's autoFocus runs while the dialog is still hidden and silently fails, and showModal
      // then focuses the first control (the close button). A field that should be ready to type
      // in says so with data-autofocus, and gets focus here, once the dialog is showing.
      dialog.querySelector<HTMLElement>("[data-autofocus]")?.focus();
    }
    if (!open && dialog.open) {
      if (typeof dialog.close === "function") dialog.close();
      else dialog.removeAttribute("open");
    }
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        dismiss();
      }}
      onMouseDown={(event) => {
        pressedBackdrop.current = event.target === ref.current;
      }}
      onClick={(event) => {
        if (event.target === ref.current && pressedBackdrop.current) dismiss();
      }}
      className="m-auto w-[min(32rem,calc(100%-2rem))] rounded-card border border-line bg-surface p-0 text-ink shadow-xl backdrop:bg-ink/40"
    >
      {open && (
        <div className="p-5 sm:p-6">
          <div className="flex items-start justify-between gap-4">
            <h2 id={titleId} className="font-display text-lg font-semibold">
              {title}
            </h2>
            <button
              type="button"
              onClick={dismiss}
              disabled={!dismissible}
              aria-label="Close"
              className="-mr-1.5 -mt-1.5 flex h-9 w-9 items-center justify-center rounded text-ink-secondary hover:bg-surface-2 hover:text-ink disabled:opacity-40"
            >
              ✕
            </button>
          </div>
          <div className="mt-4">{children}</div>
        </div>
      )}
    </dialog>
  );
}
