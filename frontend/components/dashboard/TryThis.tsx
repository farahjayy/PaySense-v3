"use client";

import Link from "next/link";

import { Card, CardCaption, CardTitle } from "@/components/ui/Card";
import { SUGGESTED_PROMPTS } from "@/lib/assistant";
import { useOpenAssistant } from "@/lib/assistantLauncher";

const STEPS = [SUGGESTED_PROMPTS[0], SUGGESTED_PROMPTS[1]] as const;

/** A guided first run for a visitor or a judge (WP7): afford -> safest option -> confirm. */
export function TryThis() {
  const open = useOpenAssistant();
  if (!open) return null;
  return (
    <Card>
      <CardTitle>Try this</CardTitle>
      <CardCaption>
        Three steps with the assistant. Each question opens it ready to send.
      </CardCaption>
      <ol className="mt-3 space-y-2 text-[14px] text-ink">
        {STEPS.map((prompt, index) => (
          <li key={prompt} className="flex items-start gap-2">
            <span aria-hidden className="mt-0.5 font-semibold text-accent">
              {index + 1}.
            </span>
            <button
              type="button"
              onClick={() => open(prompt)}
              className="rounded-full border border-line bg-surface-2 px-3 py-1 text-left text-[13px] hover:bg-accent-bg"
            >
              {index === 0 ? "Ask: " : "Then: "}
              {prompt}
            </button>
          </li>
        ))}
        <li className="flex items-start gap-2">
          <span aria-hidden className="mt-0.5 font-semibold text-accent">
            3.
          </span>
          <span>
            If you want the plan, press Confirm on its card. Nothing changes until you press
            Confirm.
          </span>
        </li>
      </ol>
      <p className="mt-3 text-[12px] text-ink-secondary">
        Have savings you could fall back on? Enter them under{" "}
        <Link href="/account" className="font-medium text-accent hover:underline">
          Your data
        </Link>{" "}
        and ask again: the forecast starts from them.
      </p>
    </Card>
  );
}
