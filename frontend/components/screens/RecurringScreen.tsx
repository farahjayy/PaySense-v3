"use client";

import { useState } from "react";

import { CADENCE_LABEL, RecurringForm } from "@/components/recurring/RecurringForm";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardCaption, CardTitle } from "@/components/ui/Card";
import { Dialog } from "@/components/ui/Dialog";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/States";
import {
  useCreateRecurring,
  useDeleteRecurring,
  useForecast,
  useRecurringItems,
  useSuggestions,
  useUpdateRecurring,
  type RecurringInput,
  type RecurringItem,
  type Suggestion,
} from "@/lib/api/queries";
import { formatDate, formatPercent } from "@/lib/format";
import { formatRm } from "@/lib/money";

type Dialogue = { kind: "add" } | { kind: "edit"; item: RecurringItem };

export function RecurringScreen() {
  const items = useRecurringItems();
  const forecast = useForecast();
  const create = useCreateRecurring();
  const update = useUpdateRecurring();
  const remove = useDeleteRecurring();
  const [dialogue, setDialogue] = useState<Dialogue | null>(null);

  const unmatched = forecast.data?.unmatched_items ?? [];

  function close() {
    setDialogue(null);
    create.reset();
    update.reset();
  }

  function save(input: RecurringInput) {
    if (dialogue?.kind === "edit") {
      const { name, amount_sen, cadence, custom_interval_days, anchor_date } = input;
      update.mutate(
        {
          id: dialogue.item.id,
          patch: { name, amount_sen, cadence, custom_interval_days, anchor_date },
        },
        { onSuccess: close },
      );
    } else {
      create.mutate(input, { onSuccess: close });
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeader
        title="Recurring items"
        intro="Bills and income that repeat. Confirmed items are counted in your forecast on their schedule, so a bill that has not landed yet is not forgotten."
        actions={
          <Button variant="accent" onClick={() => setDialogue({ kind: "add" })}>
            Add an item
          </Button>
        }
      />
      {unmatched.length > 0 && (
        <Banner tone="info" title="Some items matched nothing in your ledger">
          {unmatched.join(", ")}: they are counted from their schedule alone. If you pay them under
          a different name, edit the item so its name matches your statement.
        </Banner>
      )}
      <Suggestions onConfirmed={() => items.refetch()} />
      <section aria-labelledby="your-items">
        <h2 id="your-items" className="mb-2 text-sm font-semibold text-ink">
          Your items
        </h2>
        {items.isPending ? (
          <Skeleton lines={4} label="Loading recurring items" />
        ) : items.isError ? (
          <ErrorState message={items.error.message} onRetry={() => items.refetch()} />
        ) : items.data.length === 0 ? (
          <EmptyState title="No recurring items yet">
            Confirm a suggestion above, or add rent, a subscription or your allowance yourself.
          </EmptyState>
        ) : (
          <ul className="divide-y divide-line overflow-hidden rounded-card border border-line bg-surface">
            {items.data.map((item) => (
              <ItemRow
                key={item.id}
                item={item}
                busy={update.isPending || remove.isPending}
                onEdit={() => setDialogue({ kind: "edit", item })}
                onToggle={() => update.mutate({ id: item.id, patch: { active: !item.active } })}
                onDelete={() => remove.mutate(item.id)}
              />
            ))}
          </ul>
        )}
        {(update.error || remove.error) && (
          <Banner tone="danger" className="mt-3" title="That change was not saved">
            {update.error?.message ?? remove.error?.message}
          </Banner>
        )}
      </section>
      <Dialog
        open={dialogue !== null}
        title={dialogue?.kind === "edit" ? "Edit recurring item" : "Add a recurring item"}
        onClose={close}
      >
        {dialogue && (
          <RecurringForm
            initial={dialogue.kind === "edit" ? dialogue.item : undefined}
            saving={create.isPending || update.isPending}
            error={create.error?.message ?? update.error?.message ?? null}
            onSubmit={save}
            onCancel={close}
          />
        )}
      </Dialog>
    </div>
  );
}

function Suggestions({ onConfirmed }: { onConfirmed: () => void }) {
  const suggestions = useSuggestions();
  const create = useCreateRecurring();
  if (suggestions.isPending || suggestions.isError || suggestions.data.length === 0) return null;

  function confirm(s: Suggestion) {
    create.mutate(
      {
        kind: s.kind,
        name: s.display_name,
        amount_sen: s.amount_sen,
        cadence: s.cadence,
        anchor_date: s.anchor_date,
        active: true,
        origin: "detected",
        match_text: s.name,
      },
      { onSuccess: onConfirmed },
    );
  }

  return (
    <Card>
      <CardTitle>We noticed these repeating</CardTitle>
      <CardCaption>
        Confirm the ones that are real. Nothing is counted in your forecast until you do.
      </CardCaption>
      <ul className="mt-3 divide-y divide-line">
        {suggestions.data.map((s) => (
          <li key={`${s.kind}-${s.name}`} className="flex items-center gap-3 py-2.5">
            <div className="min-w-0 flex-1">
              <p className="truncate text-[14px] font-medium text-ink">{s.display_name}</p>
              <p className="text-[12px] text-ink-secondary">
                {s.kind === "income" ? "Income" : "Bill"} · {formatRm(s.amount_sen)} ·{" "}
                {CADENCE_LABEL[s.cadence].toLowerCase()} · seen {s.occurrences} times (
                {formatPercent(s.confidence)} sure)
              </p>
            </div>
            <Button
              variant="accent"
              size="sm"
              disabled={create.isPending}
              onClick={() => confirm(s)}
              aria-label={`Confirm ${s.display_name}`}
            >
              Confirm
            </Button>
          </li>
        ))}
      </ul>
      {create.error && (
        <Banner tone="danger" className="mt-3" title="Not confirmed">
          {create.error.message}
        </Banner>
      )}
    </Card>
  );
}

type RowProps = {
  item: RecurringItem;
  busy: boolean;
  onEdit: () => void;
  onToggle: () => void;
  onDelete: () => void;
};

function ItemRow({ item, busy, onEdit, onToggle, onDelete }: RowProps) {
  return (
    <li
      className={`flex flex-wrap items-center gap-3 px-4 py-3 ${item.active ? "" : "bg-surface-2"}`}
    >
      <div className="min-w-0 flex-1">
        <p
          className={`truncate text-[14px] font-medium ${item.active ? "text-ink" : "text-ink-muted"}`}
        >
          {item.name}
          {!item.active && <span className="ml-2 text-[12px] font-normal">paused</span>}
        </p>
        <p className="text-[12px] text-ink-secondary">
          {item.kind === "income" ? "Income" : "Bill"} · {CADENCE_LABEL[item.cadence].toLowerCase()}
          {item.cadence === "custom" && ` (${item.custom_interval_days} days)`} · from{" "}
          {formatDate(item.anchor_date)}
        </p>
      </div>
      <span className="text-[14px] font-semibold tabular-nums">{formatRm(item.amount_sen)}</span>
      <div className="flex gap-1">
        <Button variant="secondary" size="sm" onClick={onEdit} aria-label={`Edit ${item.name}`}>
          Edit
        </Button>
        <Button
          variant="secondary"
          size="sm"
          disabled={busy}
          onClick={onToggle}
          aria-label={`${item.active ? "Pause" : "Resume"} ${item.name}`}
        >
          {item.active ? "Pause" : "Resume"}
        </Button>
        <Button
          variant="secondary"
          size="sm"
          disabled={busy}
          onClick={onDelete}
          aria-label={`Delete ${item.name}`}
        >
          Delete
        </Button>
      </div>
    </li>
  );
}
