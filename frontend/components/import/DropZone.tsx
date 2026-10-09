"use client";

import { useRef, useState } from "react";

import { Button } from "@/components/ui/Button";

type Props = { onFile: (file: File) => void; busy: boolean };

/** Drag-and-drop target with a real button behind it, so the keyboard does everything the mouse does. */
export function DropZone({ onFile, busy }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function take(files: FileList | null) {
    const file = files?.[0];
    if (file) onFile(file);
  }

  return (
    <div
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        take(event.dataTransfer.files);
      }}
      className={`flex flex-col items-center gap-3 rounded-card border-2 border-dashed px-6 py-12 text-center transition-colors ${
        dragging ? "border-accent bg-accent-bg" : "border-line bg-surface"
      }`}
    >
      <p className="font-serif text-lg font-semibold text-ink">Drop a statement here</p>
      <p className="max-w-sm text-[13px] leading-relaxed text-ink-secondary">
        A CSV exported from your bank or e-wallet, up to 5 MB. Nothing is saved until you have
        reviewed it.
      </p>
      <input
        ref={input}
        type="file"
        accept=".csv,text/csv"
        className="sr-only"
        aria-label="Choose a CSV file"
        tabIndex={-1}
        onChange={(event) => {
          take(event.target.files);
          event.target.value = "";
        }}
      />
      <Button variant="accent" disabled={busy} onClick={() => input.current?.click()}>
        {busy ? "Reading…" : "Choose a file"}
      </Button>
    </div>
  );
}
