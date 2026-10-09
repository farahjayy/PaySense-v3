import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardCaption, CardTitle } from "@/components/ui/Card";
import type { PlanInput, RiskCheck } from "@/lib/api/queries";
import { formatPercent } from "@/lib/format";

type Props = {
  suggestion: NonNullable<RiskCheck["suggestion"]>;
  /** Absent on a saved report, where the suggestion is shown but cannot be tried. */
  onTry?: (request: PlanInput) => void;
  busy?: boolean;
};

/** The smallest change that reaches Safe, or an honest statement that none in the grid does. */
export function SuggestionCard({ suggestion, onTry, busy = false }: Props) {
  if (suggestion.status === "already_safe") return null;
  const found = suggestion.status === "found";
  return (
    <Card>
      <CardTitle>
        {found ? "What would make this safer" : "No single change gets this to Safe"}
      </CardTitle>
      <CardCaption>
        {found
          ? "The smallest change we tried that brings the risk under 10%."
          : `We tried ${suggestion.evaluated} combinations of more instalments, waiting for your next income, a lower price and another provider.`}
      </CardCaption>
      {suggestion.changes.length > 0 ? (
        <div className="mt-3 space-y-3">
          <ul className="list-disc space-y-1 pl-5 text-[14px] text-ink">
            {suggestion.changes.map((change) => (
              <li key={`${change.kind}-${change.label}`}>{change.label}</li>
            ))}
          </ul>
          {suggestion.probability !== null && suggestion.band && (
            <p className="text-[13px] text-ink-secondary">
              {found
                ? "That would put the chance of running short at"
                : "The best we found still leaves it at"}{" "}
              {formatPercent(suggestion.probability)} ({suggestion.band}).
            </p>
          )}
          {onTry && suggestion.request && (
            <Button
              variant="secondary"
              size="sm"
              disabled={busy}
              onClick={() => suggestion.request && onTry(suggestion.request)}
            >
              Try this
            </Button>
          )}
        </div>
      ) : (
        <Banner tone="info" className="mt-3">
          Nothing we tried helps. The most useful thing is probably to wait, or to look for
          something cheaper.
        </Banner>
      )}
    </Card>
  );
}
