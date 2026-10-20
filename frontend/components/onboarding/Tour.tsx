"use client";

import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type KeyboardEvent } from "react";

import { Button } from "@/components/ui/Button";

type Stop = { target: string; title: string; text: string };

// Each stop points at the element marked data-tour="<target>"; a stop with nothing on screen when
// the tour opens is left out (the forecast is only on the dashboard). The tour is lazy-loaded, so
// it always mounts after the page it points at.
const STOPS: readonly Stop[] = [
  {
    target: "forecast",
    title: "Where your money is heading",
    text: "Your health score and the next few months, played forward from your own records.",
  },
  {
    target: "import",
    title: "Start here",
    text: "Bring in a bank or e-wallet statement. You review it before anything is saved.",
  },
  {
    target: "risk",
    title: "Check before you split",
    text: "Describe a pay-later buy and see whether it fits, before you commit.",
  },
  {
    target: "ask",
    title: "Ask PaySense",
    text: "Ask in your own words. Nothing in your data changes until you press Confirm.",
  },
  {
    target: "data",
    title: "Your data",
    text: "Download or delete everything PaySense holds about you, any time.",
  },
];

/** The marked element that is actually on screen: the sidebar on a laptop, the bottom bar on a phone. */
function find(target: string): HTMLElement | null {
  for (const el of document.querySelectorAll<HTMLElement>(`[data-tour="${target}"]`)) {
    const box = el.getBoundingClientRect();
    if (box.width > 0 && box.height > 0) return el;
  }
  return null;
}

const PAD = 6; // spotlight margin around the target
const GAP = 14; // spotlight to bubble, room for the arrow
const EDGE = 16;

type Box = { top: number; left: number; width: number; height: number };

/**
 * Where the bubble and its arrow go: to the right of a narrow target near the left edge (the
 * sidebar), else below it, else above it. Kept inside the viewport.
 */
function place(box: Box) {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const width = Math.min(300, vw - 2 * EDGE);
  const clamp = (n: number, lo: number, hi: number) => Math.min(Math.max(n, lo), hi);
  const midX = box.left + box.width / 2;
  const midY = box.top + box.height / 2;
  if (box.width < 280 && box.left + box.width + GAP + width + EDGE <= vw) {
    const top = clamp(midY - 48, EDGE, vh - 220);
    return {
      side: "right" as const,
      bubble: { left: box.left + box.width + PAD + GAP, top, width },
      arrow: { top: clamp(midY - top, 20, 200) },
    };
  }
  const left = clamp(midX - width / 2, EDGE, vw - EDGE - width);
  const arrow = { left: clamp(midX - left, 20, width - 20) };
  if (vh - (box.top + box.height) > 230) {
    return { side: "below" as const, bubble: { left, top: box.top + box.height + PAD + GAP, width }, arrow };
  }
  return { side: "above" as const, bubble: { left, bottom: vh - box.top + PAD + GAP, width }, arrow };
}

// The arrow is a rotated square on the bubble's edge facing the target.
const ARROW: Record<ReturnType<typeof place>["side"], string> = {
  right: "-left-1.5 -translate-y-1/2",
  below: "-top-1.5 -translate-x-1/2",
  above: "-bottom-1.5 -translate-x-1/2",
};

/**
 * A guided tour of the app itself: the screen dims, a spotlight moves from one real control to the
 * next, and a bubble with an arrow says what each one is for. Opens once per browser, on the
 * dashboard after onboarding, and again after a replay of the intro.
 */
export function Tour({ onDone }: { onDone: () => void }) {
  const [stops] = useState(() => STOPS.filter((stop) => find(stop.target)));
  const [index, setIndex] = useState(0);
  const [box, setBox] = useState<Box | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const stop = stops[index];

  useEffect(() => {
    if (!stops.length) onDone();
  }, [stops, onDone]);

  // Follow the target while it scrolls into view, the window resizes, or its content loads. Measured
  // before paint, so the bubble never shows in the wrong place.
  useLayoutEffect(() => {
    const el = stop && find(stop.target);
    if (!el) return;
    el.scrollIntoView?.({ block: "center", behavior: "smooth" });
    let frame = 0;
    const read = () => {
      const r = el.getBoundingClientRect();
      setBox({ top: r.top - PAD, left: r.left - PAD, width: r.width + 2 * PAD, height: r.height + 2 * PAD });
    };
    const measure = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(read);
    };
    read();
    const resize = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    resize?.observe(el);
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    heading.current?.focus();
    return () => {
      cancelAnimationFrame(frame);
      resize?.disconnect();
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [stop]);

  if (!stop) return null;
  const last = index === stops.length - 1;
  const go = (to: number) => setIndex(Math.min(Math.max(to, 0), stops.length - 1));
  const spot = box && place(box);

  function onKeyDown(event: KeyboardEvent) {
    if (event.key === "ArrowRight") go(index + 1);
    if (event.key === "ArrowLeft") go(index - 1);
    if (event.key === "Escape") onDone();
  }

  return (
    <div role="dialog" aria-modal aria-label="Tour of PaySense" onKeyDown={onKeyDown} className="fixed inset-0 z-50">
      {box && <div aria-hidden className="tour-spot pointer-events-none fixed rounded-2xl" style={box} />}
      <div
        key={index}
        style={spot ? (spot.bubble as CSSProperties) : { visibility: "hidden" }}
        className="tour-in fixed rounded-2xl bg-surface p-4 shadow-2xl"
      >
        {spot && (
          <span
            aria-hidden
            style={spot.arrow}
            className={`absolute size-3 rotate-45 rounded-[2px] bg-surface ${ARROW[spot.side]}`}
          />
        )}
        <p className="text-[12px] font-semibold text-accent">
          {index + 1} of {stops.length}
        </p>
        <h2 ref={heading} tabIndex={-1} className="mt-1 font-display text-[18px] font-bold text-ink outline-none">
          {stop.title}
        </h2>
        <p className="mt-1 text-[14px] leading-relaxed text-ink-secondary">{stop.text}</p>
        <div className="mt-4 flex items-center gap-2">
          <button
            type="button"
            onClick={onDone}
            className="mr-auto rounded-lg px-1 text-[13px] font-semibold text-ink-muted hover:text-ink"
          >
            Skip tour
          </button>
          {index > 0 && (
            <Button variant="secondary" size="sm" onClick={() => go(index - 1)}>
              Back
            </Button>
          )}
          <Button variant="accent" size="sm" onClick={last ? onDone : () => go(index + 1)}>
            {last ? "Done" : "Next"}
          </Button>
        </div>
      </div>
    </div>
  );
}
