"use client";

import { ConfirmCard } from "@/components/assistant/ConfirmCard";
import { ResultCard } from "@/components/assistant/ResultCard";
import {
  STATUS_LABEL,
  TIER_LABEL,
  describeInputs,
  toolLabel,
  type ChatReply,
  type Step,
} from "@/lib/assistant";

/** "What I did": every tool call, its permission tier, what it was given and how it went. */
export function StepsList({ steps }: { steps: Step[] }) {
  if (steps.length === 0) return null;
  return (
    <details className="rounded-lg border border-line bg-surface-2 px-3 py-2 text-[12px]">
      <summary className="cursor-pointer font-medium text-ink">
        What I did ({steps.length} {steps.length === 1 ? "step" : "steps"})
      </summary>
      <ol className="mt-2 space-y-2">
        {steps.map((step, i) => (
          <li key={`${step.tool}-${i}`}>
            <p className="font-medium text-ink">
              {toolLabel(step.tool)}{" "}
              <span className="rounded bg-surface px-1.5 py-0.5 text-[11px] text-ink-secondary">
                {TIER_LABEL[step.tier]}
              </span>{" "}
              <span className={step.status === "ok" ? "text-success" : "text-danger"}>
                {STATUS_LABEL[step.status]}
              </span>
            </p>
            <p className="text-ink-secondary">{step.summary}</p>
            {Object.keys(step.inputs).length > 0 && (
              <p className="text-ink-muted">{describeInputs(step.inputs).join(" · ")}</p>
            )}
          </li>
        ))}
      </ol>
    </details>
  );
}

/** One assistant turn: the short reply, what was done, the result cards and any proposal. */
export function AssistantMessage({ reply }: { reply: ChatReply }) {
  return (
    <div className="space-y-2.5">
      <p className="whitespace-pre-line text-[14px] leading-relaxed text-ink">
        {reply.reply.replace(/\*\*/g, "")}
      </p>
      {reply.narration_replaced && (
        <p className="text-[11px] text-ink-muted">
          The model&apos;s wording used a figure no tool gave, so a plain summary is shown instead.
        </p>
      )}
      <StepsList steps={reply.steps} />
      {reply.cards.map((card, i) => (
        <ResultCard key={`${card.kind}-${i}`} card={card} />
      ))}
      {reply.pending_actions.map((action) => (
        <ConfirmCard key={action.id} action={action} />
      ))}
    </div>
  );
}
