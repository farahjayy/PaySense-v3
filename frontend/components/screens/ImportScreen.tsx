"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { DropZone } from "@/components/import/DropZone";
import { ReviewList } from "@/components/import/ReviewList";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatTile } from "@/components/ui/StatTile";
import { ApiError, useImportConfirm, useImportPreview } from "@/lib/api/queries";
import { useAssignableCategories } from "@/lib/categories";
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
  const [notes, setNotes] = useState<string[]>([]);
  const [fileCategories, setFileCategories] = useState<string[]>([]);
  const categories = useAssignableCategories(fileCategories);
  const [problem, setProblem] = useState<string | null>(null);
  const [created, setCreated] = useState<number | null>(null);

  function reset() {
    setRows(null);
    setSkipped([]);
    setNotes([]);
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
        setNotes(result.notes);
        // Taken from the file as it arrived, so a category stays on offer after a row is changed.
        setFileCategories(result.rows.map((r) => r.category_guess));
      },
    });
  }

  function handleConfirm() {
    if (!rows) return;
    confirm.mutate(toConfirmRows(rows), {
      onSuccess: (result) => setCreated(result.created),
    });
  }

  // When the screen changes step the old controls disappear; move focus to the new step so a
  // keyboard or screen-reader user is not dropped at the top of the document.
  const step = created !== null ? "done" : rows ? "review" : "pick";
  const stepRef = useRef<HTMLDivElement>(null);
  const firstStep = useRef(true);
  useEffect(() => {
    if (firstStep.current) {
      firstStep.current = false;
      return;
    }
    stepRef.current?.focus();
  }, [step]);

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title="Import"
        intro="Bring in a bank or e-wallet statement, or your own spreadsheet. You review everything before it is saved."
      />
      <div ref={stepRef} tabIndex={-1} className="outline-none">
        {created !== null ? (
          <Done created={created} onAnother={reset} />
        ) : rows ? (
          <Review
            rows={rows}
            skipped={skipped}
            notes={notes}
            categories={categories}
            onChange={(row, patch) => setRows((current) => patchRow(current ?? [], row, patch))}
            onAll={(include) => setRows((current) => setAllIncluded(current ?? [], include))}
            onConfirm={handleConfirm}
            onCancel={reset}
            saving={confirm.isPending}
            saveError={confirm.error?.message ?? null}
            networkLost={
              confirm.error instanceof ApiError && confirm.error.code === "network_error"
            }
          />
        ) : (
          <div className="space-y-4">
            <DropZone onFile={handleFile} busy={preview.isPending} />
            <p className="text-[12px] leading-relaxed text-ink-secondary">
              We read CSV and Excel files, not PDFs. If your bank only gives a PDF statement,
              convert it to CSV or Excel first, then check the descriptions and categories in the
              review step.{" "}
              <a
                href="/paysense-import-template.csv"
                download
                className="font-semibold text-accent underline-offset-2 hover:underline"
              >
                Download the import template
              </a>{" "}
              (type, date, item, amount, category) to see the layout that always imports cleanly.
            </p>
            {(problem ?? preview.error?.message) && (
              <Banner tone="danger" title="That file could not be used">
                {problem ?? preview.error?.message}
              </Banner>
            )}
          </div>
        )}
      </div>
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
  notes: readonly string[];
  categories: readonly string[];
  onChange: (row: number, patch: Partial<Pick<ReviewRow, "category" | "type" | "include">>) => void;
  onAll: (include: boolean) => void;
  onConfirm: () => void;
  onCancel: () => void;
  saving: boolean;
  saveError: string | null;
  networkLost: boolean;
};

function Review({
  rows,
  skipped,
  notes,
  categories,
  onChange,
  onAll,
  onConfirm,
  onCancel,
  saving,
  saveError,
  networkLost,
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
      {notes.length > 0 && (
        <Banner tone="info" title="Part of the file was not read">
          <ul className="list-disc pl-4">
            {notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </Banner>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="secondary" size="sm" onClick={() => onAll(true)}>
          Tick all
        </Button>
        <Button variant="secondary" size="sm" onClick={() => onAll(false)}>
          Untick all
        </Button>
        <p className="text-[12px] text-ink-secondary">
          Only ticked rows are saved. Untick a row to leave it out.
        </p>
      </div>
      <ReviewList rows={rows} categories={categories} onChange={onChange} />
      {saveError && (
        <Banner
          tone="danger"
          title={networkLost ? "We could not confirm this was saved" : "Nothing was saved"}
        >
          {saveError}
          {networkLost && " Check Transactions before trying again, so nothing is added twice."}
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
