"use client";

import { useState } from "react";

import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardCaption, CardTitle } from "@/components/ui/Card";
import { MoneyInput } from "@/components/ui/MoneyInput";
import { Skeleton } from "@/components/ui/States";
import { useProviderLimits, useSetProviderLimit, type ProviderLimit } from "@/lib/api/queries";
import { formatRm } from "@/lib/money";

const LABEL: Record<ProviderLimit["provider"], string> = {
  spaylater: "SPayLater",
  tiktok_paylater: "TikTok PayLater",
  atome: "Atome",
};

/**
 * Your credit limit per provider, as you read it in that app. It caps how much of a new purchase
 * is financed; the rest is paid at checkout. Nothing is guessed: with no limit recorded, no cap.
 */
export function ProviderLimits() {
  const limits = useProviderLimits();
  return (
    <Card>
      <CardTitle>Your BNPL limits</CardTitle>
      <CardCaption>
        Copy each limit from the provider&apos;s app. When a new purchase is more than what is left,
        the provider pays the shop up to your remaining limit and you pay the rest yourself at
        checkout. The risk check uses this, so it only counts what the provider would really
        finance.
      </CardCaption>
      <div className="mt-4 space-y-4">
        {limits.isPending ? (
          <Skeleton lines={3} label="Loading limits" />
        ) : limits.isError ? (
          <Banner tone="danger" title="Limits did not load">
            {limits.error.message}
          </Banner>
        ) : (
          limits.data.map((limit) => <LimitRow key={limit.provider} limit={limit} />)
        )}
      </div>
    </Card>
  );
}

function LimitRow({ limit }: { limit: ProviderLimit }) {
  const save = useSetProviderLimit();
  const [sen, setSen] = useState<number | null>(limit.limit_sen);
  const unchanged = sen === limit.limit_sen;

  return (
    <div className="flex flex-wrap items-end gap-3">
      <div className="w-44">
        <MoneyInput label={`${LABEL[limit.provider]} limit`} valueSen={sen} onChange={setSen} />
      </div>
      <Button
        variant="secondary"
        disabled={sen === null || unchanged || save.isPending}
        onClick={() => sen !== null && save.mutate({ provider: limit.provider, limitSen: sen })}
        aria-label={`Save ${LABEL[limit.provider]} limit`}
      >
        {save.isPending ? "Saving…" : "Save"}
      </Button>
      <p className="pb-2 text-[12px] text-ink-secondary" aria-live="polite">
        {limit.limit_sen === null
          ? "No limit recorded"
          : `${formatRm(limit.used_sen)} in use, ${formatRm(limit.remaining_sen ?? 0)} left`}
      </p>
      {save.error && (
        <p role="alert" className="w-full text-[12px] font-medium text-danger">
          {save.error.message}
        </p>
      )}
    </div>
  );
}
