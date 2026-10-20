"use client";

import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardCaption, CardTitle } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { useSecurityDrill, type Drill } from "@/lib/api/queries";
import { plural } from "@/lib/format";

type AttackClass = Drill["attacks"][number]["attack_class"];
type Attack = Drill["attacks"][number];

const CLASS_LABEL: Record<AttackClass, string> = {
  induced_transfers: "Induced transfers",
  data_extraction: "Data extraction",
  privilege_escalation: "Privilege escalation",
  prompt_injection: "Prompt injection",
};

const CLASS_LINE: Record<AttackClass, string> = {
  induced_transfers:
    "Getting money moved or records written without the person's say-so.",
  data_extraction: "Getting another student's data out, or inventing it.",
  privilege_escalation: "Getting the model to do what only the person may do.",
  prompt_injection: "Hiding instructions in data the model reads.",
};

/**
 * The security drill (ADR D-58): the four named attack classes, run on request against a
 * throwaway sandbox on the server. Every figure comes from the drill's response.
 */
export function SecurityScreen() {
  const drill = useSecurityDrill();
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <PageHeader
        title="Security drill"
        intro="Attack the assistant on purpose, and see what the attacker got the model to do and what actually happened to the data."
      />
      <Card>
        <CardTitle>Run an attack on the assistant</CardTitle>
        <details className="mt-2 text-[14px] leading-relaxed text-ink-secondary">
          <summary className="w-fit cursor-pointer rounded font-semibold text-accent">
            How the drill works
          </summary>
          <ul className="mt-2 list-disc space-y-1.5 pl-5 text-[14px] leading-relaxed text-ink-secondary">
            <li>
              It runs on the server in a throwaway sandbox with two made-up
              students. Your own data is never read or written.
            </li>
            <li>
              The model is a script that obeys every instruction it is given, so
              it is fooled every time: the worst case. The defences have to hold
              without the model&apos;s help.
            </li>
            <li>
              Harm is checked on the sandbox after each attack: records written
              without a confirm, another student&apos;s data in anything returned,
              a made-up figure reaching the reply.
            </li>
            <li>
              How the real model behaves is measured separately in the assistant
              evaluation (`reports/assistant/` in the repository).
            </li>
          </ul>
        </details>
        <Button
          className="mt-4"
          variant="accent"
          disabled={drill.isPending}
          onClick={() => drill.mutate()}
        >
          {drill.isPending
            ? "Running…"
            : drill.data
              ? "Run it again"
              : "Run the drill"}
        </Button>
      </Card>
      {drill.error && (
        <Banner tone="danger" title="The drill did not run">
          {drill.error.message}
        </Banner>
      )}
      {drill.data && <Result drill={drill.data} />}
    </div>
  );
}

function Result({ drill }: { drill: Drill }) {
  const attacks = drill.totals.reduce((n, t) => n + t.attacks, 0);
  const fooled = drill.totals.reduce((n, t) => n + t.fooled, 0);
  const harmed = drill.totals.reduce((n, t) => n + t.harmed, 0);
  return (
    <section aria-label="Drill result" className="space-y-4">
      {harmed === 0 ? (
        <Banner
          tone="success"
          title={`${fooled} of ${attacks} attacks fooled the model`}
        >
          No harm done in any of them. Ran in{" "}
          {(drill.duration_ms / 1000).toFixed(1)} s.
        </Banner>
      ) : (
        <Banner tone="danger" title={`${plural(harmed, "attack")} did harm`}>
          The drill reports this as found, not hidden. See the attacks marked
          below.
        </Banner>
      )}
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[13px]">
            <caption className="mb-2 text-left text-sm font-semibold text-ink">
              Scoreboard
            </caption>
            <thead className="text-[12px] text-ink-secondary">
              <tr className="border-b border-line">
                <th scope="col" className="py-1.5 pr-3 font-medium">
                  Attack class
                </th>
                <th scope="col" className="py-1.5 pr-3 text-right font-medium">
                  Attacks
                </th>
                <th scope="col" className="py-1.5 pr-3 text-right font-medium">
                  Model fooled
                </th>
                <th scope="col" className="py-1.5 text-right font-medium">
                  Harm done
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {drill.totals.map((t) => (
                <tr key={t.attack_class}>
                  <th scope="row" className="py-2 pr-3 font-medium text-ink">
                    {CLASS_LABEL[t.attack_class]}
                  </th>
                  <td className="py-2 pr-3 text-right tabular-nums">
                    {t.attacks}
                  </td>
                  <td className="py-2 pr-3 text-right tabular-nums">
                    {t.fooled}
                  </td>
                  <td
                    className={`py-2 text-right font-semibold tabular-nums ${t.harmed ? "text-danger" : "text-success"}`}
                  >
                    {t.harmed}
                  </td>
                </tr>
              ))}
              <tr className="border-t border-line">
                <th scope="row" className="py-2 pr-3 font-semibold text-ink">
                  Total
                </th>
                <td className="py-2 pr-3 text-right font-semibold tabular-nums">
                  {attacks}
                </td>
                <td className="py-2 pr-3 text-right font-semibold tabular-nums">
                  {fooled}
                </td>
                <td className="py-2 text-right font-semibold tabular-nums">
                  {harmed}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </Card>
      {drill.totals.map((t) => (
        <ClassAttacks
          key={t.attack_class}
          attackClass={t.attack_class}
          attacks={drill.attacks.filter(
            (a) => a.attack_class === t.attack_class,
          )}
        />
      ))}
    </section>
  );
}

function ClassAttacks({
  attackClass,
  attacks,
}: {
  attackClass: AttackClass;
  attacks: Attack[];
}) {
  const id = `drill-${attackClass}`;
  return (
    <Card>
      <section aria-labelledby={id}>
        <h2 id={id} className="text-sm font-semibold text-ink">
          {CLASS_LABEL[attackClass]}
        </h2>
        <CardCaption>{CLASS_LINE[attackClass]}</CardCaption>
        <ul className="mt-3 divide-y divide-line rounded-lg border border-line">
          {attacks.map((a) => (
            <li key={a.id} className="px-3.5 py-2.5 text-[13px]">
              <details>
                <summary className="flex cursor-pointer flex-wrap items-center justify-between gap-2">
                  <span className="font-medium text-ink">{a.title}</span>
                  <span className="flex gap-1.5 text-[12px]">
                    {a.fooled && (
                      <span className="rounded-full bg-warning-bg px-2 py-0.5 text-ink">
                        Model fooled
                      </span>
                    )}
                    <span
                      className={`rounded-full px-2 py-0.5 font-semibold ${a.harmed ? "bg-danger-bg text-danger" : "bg-success-bg text-success"}`}
                    >
                      {a.harmed ? "Harm done" : "No harm"}
                    </span>
                  </span>
                </summary>
                <dl className="mt-2 space-y-1.5 text-ink-secondary">
                  <div>
                    <dt className="font-medium text-ink">
                      What the attacker made the model do
                    </dt>
                    <dd>{a.tried}</dd>
                  </div>
                  <div>
                    <dt className="font-medium text-ink">What stops it</dt>
                    <dd>{a.stopped_by}</dd>
                  </div>
                  <div>
                    <dt className="font-medium text-ink">
                      What was checked afterwards
                    </dt>
                    <dd>{a.evidence}</dd>
                  </div>
                </dl>
              </details>
            </li>
          ))}
        </ul>
      </section>
    </Card>
  );
}
