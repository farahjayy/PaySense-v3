"use client";

import Link from "next/link";
import { useState } from "react";

import { DropZone } from "@/components/import/DropZone";
import { ReviewList } from "@/components/import/ReviewList";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatTile } from "@/components/ui/StatTile";
import { useImportConfirm, useImportPreview } from "@/lib/api/queries";
import { plural } from "@/lib/format";
import {
  fileProblem,
  patchRow,
  setAllIncluded,
  toConfirmRows,
  toReviewRows,
  totals,
  type ReviewRow,
} from "@/lib/import";
import { formatRm } from "@/lib/money";

type Skipped = { row: number; reason: string };

export function ImportScreen() {
  const preview = useImportPreview();
  const confirm = useImportConfirm();
  const [rows, setRows] = useState<ReviewRow[] | null>(null);
  const [skipped, setSkipped] = useState<Skipped[]>([]);
  const [problem, setProblem] = useState<string | null>(null);
  const [created, setCreated] = useState<number | null>(null);

  function reset() {
    setRows(null);
    setSkipped([]);
    setProblem(null);
    setCreated(null);
    preview.reset();
    confirm.reset();
  }

  function handleFile(file: File) {
    const found = fileProblem(file);
    setProblem(found);
    if (found) return;
    preview.mutate(file, {
      onSuccess: (result) => {
        setRows(toReviewRows(result));
        setSkipped(result.skipped);
      },
    });
  }

  function handleConfirm() {
    if (!rows) return;
    confirm.mutate(toConfirmRows(rows), {
      onSuccess: (result) => setCreated(result.created),
    });
  }

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title="Import"
        intro="Bring in a bank or e-wallet statement. You review everything before it is saved."
      />
      {created !== null ? (
        <Done created={created} onAnother={reset} />
      ) : rows ? (
        <Review
          rows={rows}
          skipped={skipped}
          onChange={(row, patch) => setRows((current) => patchRow(current ?? [], row, patch))}
          onAll={(include) => setRows((current) => setAllIncluded(current ?? [], include))}
          onConfirm={handleConfirm}
          onCancel={reset}
          saving={confirm.isPending}
          saveError={confirm.error?.message ?? null}
        />
      ) : (
        <div className="space-y-4">
          <DropZone onFile={handleFile} busy={preview.isPending} />
          {(problem ?? preview.error?.message) && (
            <Banner tone="danger" title="That file could not be used">
              {problem ?? preview.error?.message}
            </Banner>
          )}
        </div>
      )}
    </div>
  );
}

function Done({ created, onAnother }: { created: number; onAnother: () => void }) {
  return (
    <div className="space-y-4">
      <Banner tone="success" title={`${plural(created, "transaction")} added`}>
        Your forecast has been refreshed with them.
      </Banner>
      <div className="flex gap-2">
        <Link
          href="/"
          className="inline-flex h-10 items-center rounded-lg bg-ink px-4 text-[13px] font-semibold text-white hover:bg-ink/85"
        >
          See your dashboard
        </Link>
        <Button variant="secondary" onClick={onAnother}>
          Import another file
        </Button>
      </div>
    </div>
  );
}

type ReviewProps = {
  rows: readonly ReviewRow[];
  skipped: readonly Skipped[];
  onChange: (row: number, patch: Partial<Pick<ReviewRow, "category" | "type" | "include">>) => void;
  onAll: (include: boolean) => void;
  onConfirm: () => void;
  onCancel: () => void;
  saving: boolean;
  saveError: string | null;
};

function Review({
  rows,
  skipped,
  onChange,
  onAll,
  onConfirm,
  onCancel,
  saving,
  saveError,
}: ReviewProps) {
  const sums = totals(rows);
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile label="Will be added" value={sums.included} note={`of ${rows.length} rows`} />
        <StatTile label="Income" value={formatRm(sums.incomeSen)} />
        <StatTile label="Spending" value={formatRm(sums.spendSen)} />
        <StatTile
          label="Already saved"
          value={sums.duplicates}
          note={sums.duplicates > 0 ? "left out unless you tick them" : undefined}
        />
      </div>
      {skipped.length > 0 && (
        <Banner tone="warning" title={`${plural(skipped.length, "row")} could not be read`}>
          <ul className="list-disc pl-4">
            {skipped.slice(0, 5).map((s) => (
              <li key={s.row}>
                Row {s.row}: {s.reason}
              </li>
            ))}
            {skipped.length > 5 && <li>and {skipped.length - 5} more</li>}
          </ul>
        </Banner>
      )}
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" size="sm" onClick={() => onAll(true)}>
          Tick all
        </Button>
        <Button variant="secondary" size="sm" onClick={() => onAll(false)}>
          Untick all
        </Button>
      </div>
      <ReviewList rows={rows} onChange={onChange} />
      {saveError && (
        <Banner tone="danger" title="Nothing was saved">
          {saveError}
        </Banner>
      )}
      <div className="sticky bottom-20 flex justify-end gap-2 md:bottom-4">
        <Button variant="secondary" onClick={onCancel} disabled={saving}>
          Start over
        </Button>
        <Button variant="accent" onClick={onConfirm} disabled={saving || sums.included === 0}>
          {saving ? "Saving…" : `Add ${plural(sums.included, "transaction")}`}
        </Button>
      </div>
    </div>
  );
}
