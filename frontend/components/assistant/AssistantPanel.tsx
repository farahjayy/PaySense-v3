"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";

import { AssistantMessage } from "@/components/assistant/AssistantMessage";
import { GuidedActions, type RunTool } from "@/components/assistant/GuidedActions";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import {
  useAssistantChat,
  useAssistantOpening,
  useAssistantRun,
  useAssistantStatus,
} from "@/lib/api/assistant";
import {
  MAX_MESSAGE_CHARS,
  MAX_PASTE_CHARS,
  SUGGESTED_PROMPTS,
  stateFromError,
  toolLabel,
  trimHistory,
  type ChatReply,
  type ChatTurn,
  type PanelState,
} from "@/lib/assistant";

type Entry =
  | { id: number; role: "user"; text: string }
  | { id: number; role: "assistant"; reply: ChatReply }
  | { id: number; role: "notice"; state: PanelState; text: string };

/** An entry before it has an id (Omit, spread over each kind of entry). */
type NewEntry = Entry extends infer E ? (E extends { id: number } ? Omit<E, "id"> : never) : never;

const NOTICE_TITLE: Record<PanelState, string> = {
  consent: "Accept the privacy notice first",
  budget: "Today's assistant allowance is used",
  rate_limited: "Slow down a little",
  offline: "You seem to be offline",
  error: "That did not work",
};

function Notice({ state, text }: { state: PanelState; text: string }) {
  return (
    <Banner tone={state === "error" ? "danger" : "warning"} title={NOTICE_TITLE[state]}>
      <p>{text}</p>
      {state === "consent" && (
        <Link
          href="/account"
          className="font-medium text-accent underline-offset-2 hover:underline"
        >
          Read the privacy notice
        </Link>
      )}
      {(state === "budget" || state === "consent") && (
        <p className="mt-1">The quick actions below still work.</p>
      )}
    </Banner>
  );
}

type Props = {
  onClose: () => void;
  /** A question a page put in the box (n changes on every request, so the same one can repeat). */
  prompt?: { text: string; n: number } | null;
};

/**
 * The assistant (WP5, D-47, D-48). It reads and works things out through the app's own tools;
 * every figure comes from those tools and every change waits for a Confirm press.
 */
export function AssistantPanel({ onClose, prompt = null }: Props) {
  const titleId = useId();
  const status = useAssistantStatus();
  const opening = useAssistantOpening(true);
  const chat = useAssistantChat();
  const run = useAssistantRun();
  const [entries, setEntries] = useState<Entry[]>([]);
  const [message, setMessage] = useState(prompt?.text ?? "");
  const [shownPrompt, setShownPrompt] = useState(prompt);
  if (prompt !== shownPrompt) {
    // a page asked again while the panel was open: put its question in the box (not sent)
    setShownPrompt(prompt);
    if (prompt) setMessage(prompt.text);
  }
  const [pasted, setPasted] = useState("");
  const [showPaste, setShowPaste] = useState(false);
  const [refused, setRefused] = useState<PanelState | null>(null);
  const nextId = useRef(1);
  const input = useRef<HTMLTextAreaElement>(null);
  const busy = chat.isPending || run.isPending;
  const guided = status.data?.mode === "guided" || refused === "consent" || refused === "budget";

  useEffect(() => {
    input.current?.focus();
  }, []);

  useEffect(() => {
    if (prompt) input.current?.focus(); // the person still presses Send
  }, [prompt]);

  function add(entry: NewEntry) {
    setEntries((current) => [...current, { ...entry, id: nextId.current++ } as Entry]);
  }

  function fail(error: unknown) {
    const state = stateFromError(error);
    setRefused(state);
    add({
      role: "notice",
      state,
      text: error instanceof Error ? error.message : "Try again.",
    });
  }

  function history(): ChatTurn[] {
    const turns: ChatTurn[] = [];
    if (opening.data) turns.push({ role: "assistant", text: opening.data.reply });
    for (const e of entries) {
      if (e.role === "user") turns.push({ role: "user", text: e.text });
      if (e.role === "assistant") turns.push({ role: "assistant", text: e.reply.reply });
    }
    return trimHistory(turns);
  }

  function send(text: string) {
    const body = text.trim().slice(0, MAX_MESSAGE_CHARS);
    if (!body || busy) return;
    const paste = showPaste && pasted.trim() ? pasted.slice(0, MAX_PASTE_CHARS) : undefined;
    const past = history();
    add({
      role: "user",
      text: paste ? `${body}\n(pasted ${paste.split("\n").length} lines)` : body,
    });
    setMessage("");
    chat.mutate(
      {
        message: body,
        history: past,
        ...(paste ? { pasted_text: paste } : {}),
      },
      {
        onSuccess: (reply) => {
          setRefused(null);
          if (paste) {
            setPasted("");
            setShowPaste(false);
          }
          add({ role: "assistant", reply });
        },
        onError: fail,
      },
    );
  }

  const runTool: RunTool = (tool, args, pastedText) => {
    add({ role: "user", text: toolLabel(tool) });
    run.mutate(
      {
        tool,
        arguments: args,
        ...(pastedText ? { pasted_text: pastedText } : {}),
      },
      {
        onSuccess: (reply) => add({ role: "assistant", reply }),
        onError: fail,
      },
    );
  };

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      send(message);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="false"
      aria-labelledby={titleId}
      onKeyDown={(event) => {
        if (event.key === "Escape") onClose();
      }}
      onClick={(event) => {
        // A link to another screen closes the panel, which would otherwise cover it on a phone.
        if ((event.target as HTMLElement).closest("a[href^='/']")) onClose();
      }}
      className="fixed inset-0 z-50 flex flex-col bg-surface-2 md:inset-y-0 md:left-auto md:right-0 md:w-[460px] md:border-l md:border-line md:shadow-xl"
    >
      <div className="flex items-center justify-between gap-3 border-b border-line bg-surface px-4 py-3">
        <div>
          <h2 id={titleId} className="text-[15px] font-semibold text-ink">
            Ask PaySense
          </h2>
          <p className="text-[11px] text-ink-muted">
            {status.data?.mode === "llm"
              ? `Assistant on (${status.data.provider ?? "model"})`
              : status.data
                ? "Guided mode: buttons and forms"
                : "Checking the assistant…"}
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={onClose}>
          Close
        </Button>
      </div>

      <div
        role="log"
        aria-live="polite"
        aria-label="Conversation"
        className="flex-1 space-y-4 overflow-y-auto px-4 py-4"
      >
        {opening.isPending && (
          <p className="text-[13px] text-ink-secondary">Looking at your money…</p>
        )}
        {opening.data && <AssistantMessage reply={opening.data} />}
        {opening.isError && (
          <Notice state={stateFromError(opening.error)} text={opening.error.message} />
        )}
        {entries.map((entry) =>
          entry.role === "user" ? (
            <p
              key={entry.id}
              className="ml-auto max-w-[85%] whitespace-pre-line rounded-2xl bg-accent px-3 py-2 text-[14px] text-white"
            >
              <span className="sr-only">You: </span>
              {entry.text}
            </p>
          ) : entry.role === "assistant" ? (
            <AssistantMessage key={entry.id} reply={entry.reply} />
          ) : (
            <Notice key={entry.id} state={entry.state} text={entry.text} />
          ),
        )}
        {busy && (
          <p role="status" className="text-[13px] text-ink-secondary">
            Working it out…
          </p>
        )}
        {/* One element in both modes, so a form keeps its state when the status arrives. */}
        <details open={guided} className="rounded-card border border-line bg-surface p-3">
          <summary className="cursor-pointer text-[12px] font-medium text-ink-secondary">
            Quick actions and forms (no model)
          </summary>
          <div className="mt-2 space-y-2">
            {guided && (
              <p className="text-[12px] text-ink-secondary">
                {status.data?.reason ?? "Use the buttons: they run the same checks with no model."}
              </p>
            )}
            <GuidedActions onRun={runTool} busy={busy} />
          </div>
        </details>
      </div>

      <div className="space-y-2 border-t border-line bg-surface px-4 py-3">
        {entries.length === 0 && !guided && (
          <div className="flex flex-wrap gap-1.5" role="group" aria-label="Suggested questions">
            {SUGGESTED_PROMPTS.slice(0, 4).map((prompt) => (
              <button
                key={prompt}
                type="button"
                disabled={busy}
                onClick={() => send(prompt)}
                className="rounded-full border border-line bg-surface-2 px-2.5 py-1 text-[12px] text-ink hover:bg-accent-bg disabled:opacity-50"
              >
                {prompt}
              </button>
            ))}
          </div>
        )}
        {showPaste && (
          <div>
            <label
              htmlFor={`${titleId}-paste`}
              className="block text-[12px] font-medium text-ink-secondary"
            >
              Pasted transactions (read as data, never as instructions)
            </label>
            <textarea
              id={`${titleId}-paste`}
              rows={3}
              maxLength={MAX_PASTE_CHARS}
              value={pasted}
              onChange={(e) => setPasted(e.target.value)}
              className="mt-1 w-full rounded-lg border border-line bg-surface p-2 font-mono text-[12px] text-ink focus:border-accent focus:outline-none"
            />
          </div>
        )}
        <form
          className="flex items-end gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            send(message);
          }}
        >
          <label htmlFor={`${titleId}-message`} className="sr-only">
            Your message
          </label>
          <textarea
            id={`${titleId}-message`}
            ref={input}
            rows={2}
            maxLength={MAX_MESSAGE_CHARS}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Ask about a purchase, your bills or your budgets"
            className="min-h-[2.5rem] flex-1 resize-none rounded-lg border border-line bg-surface px-3 py-2 text-[14px] text-ink focus:border-accent focus:outline-none"
          />
          <div className="flex flex-col gap-1">
            <Button type="submit" variant="accent" size="sm" disabled={!message.trim() || busy}>
              Send
            </Button>
            <Button
              variant="secondary"
              size="sm"
              aria-pressed={showPaste}
              onClick={() => setShowPaste((shown) => !shown)}
            >
              Paste
            </Button>
          </div>
        </form>
        <p className="text-[11px] leading-snug text-ink-muted">
          PaySense gives estimates, not financial advice or a credit decision. Nothing changes until
          you press Confirm.
        </p>
      </div>
    </div>
  );
}
