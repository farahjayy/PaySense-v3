"use client";

import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/States";
import { useModelInfo } from "@/lib/api/queries";

const FAMILY: Record<string, string> = {
  lightgbm: "gradient-boosted trees",
  xgboost: "gradient-boosted trees",
  random_forest: "random forest",
  logistic: "logistic regression",
};

function percentOf(value: number | null): string {
  return value === null ? "n/a" : value.toFixed(4);
}

/** What is actually serving right now, read from the server rather than written into the page. */
export function ModelVersions() {
  const info = useModelInfo();
  if (info.isPending) return <Skeleton lines={3} label="Loading model details" />;
  if (info.isError) return null; // the rest of the page stands on its own
  const { forecast, risk } = info.data;
  return (
    <Card>
      <section aria-labelledby="versions">
        <h2 id="versions" className="font-display text-lg font-semibold text-ink">
          What is running now
        </h2>
        <dl className="mt-3 grid gap-x-6 gap-y-2 text-[14px] sm:grid-cols-[auto_1fr]">
          <dt className="text-ink-secondary">Forecast</dt>
          <dd className="text-ink">
            {forecast.model === "lstm" ? "a recurrent neural network" : forecast.model}, version{" "}
            {forecast.version}
          </dd>
          <dt className="text-ink-secondary">Risk check</dt>
          <dd className="text-ink">
            {risk.available ? (
              <>
                {FAMILY[risk.family ?? ""] ?? risk.family}, version {risk.version}, learned from{" "}
                {risk.development_profiles?.toLocaleString("en-MY")} simulated students
              </>
            ) : (
              "not available on this server"
            )}
          </dd>
          {risk.available && risk.lockbox_brier !== null && risk.constant_brier !== null && (
            <>
              <dt className="text-ink-secondary">Accuracy on students it never saw</dt>
              <dd className="text-ink">
                average squared error {percentOf(risk.lockbox_brier)}, against{" "}
                {percentOf(risk.constant_brier)} for always guessing the average. Lower is better.
              </dd>
            </>
          )}
        </dl>
      </section>
    </Card>
  );
}
