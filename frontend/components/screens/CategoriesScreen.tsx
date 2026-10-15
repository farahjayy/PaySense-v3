"use client";

import { useState } from "react";

import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { TextField } from "@/components/ui/fields";
import { PageHeader } from "@/components/ui/PageHeader";
import { ErrorState, Skeleton } from "@/components/ui/States";
import {
  useAddCategory,
  useCategories,
  useDeleteCategory,
  useRenameCategory,
  type Category,
} from "@/lib/api/queries";
import { focusPageHeading } from "@/lib/focus";
import { plural } from "@/lib/format";

type Dialogue =
  { kind: "add" } | { kind: "rename"; category: Category } | { kind: "delete"; category: Category };

// Moving spending into these would change how it counts (the server refuses it too).
const MOVE_NOT_ALLOWED = new Set(["Refund", "Transfer", "BNPL"]);
const TEMPLATE_HREF = "/paysense-import-template.csv";
const LINK_BUTTON =
  "inline-flex h-10 items-center rounded-lg border border-line bg-surface px-4 text-[13px] font-semibold text-ink hover:bg-surface-2";

function usage(count: number): string {
  return count === 0 ? "No transactions" : plural(count, "transaction");
}

export function CategoriesScreen() {
  const list = useCategories();
  const add = useAddCategory();
  const rename = useRenameCategory();
  const remove = useDeleteCategory();
  const [dialogue, setDialogue] = useState<Dialogue | null>(null);

  function close() {
    setDialogue(null);
    add.reset();
    rename.reset();
    remove.reset();
  }

  // A renamed or deleted row is gone (or re-keyed), so the dialog cannot hand focus back to it.
  function closeAndFocusHeading() {
    close();
    focusPageHeading();
  }

  const categories = list.data?.categories ?? [];
  const own = categories.filter((c) => !c.builtin);
  const builtIn = categories.filter((c) => c.builtin);

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader
        title="Categories"
        intro="The labels on your transactions. The built-in ones are fixed, because the forecast depends on a few of them (refunds, transfers, BNPL). The ones you add are yours to rename or delete."
        actions={
          <>
            <a href={TEMPLATE_HREF} download className={LINK_BUTTON}>
              Download import template
            </a>
            <Button variant="accent" onClick={() => setDialogue({ kind: "add" })}>
              Add category
            </Button>
          </>
        }
      />

      {list.isPending ? (
        <Skeleton lines={6} label="Loading categories" />
      ) : list.isError ? (
        <ErrorState message={list.error.message} onRetry={() => list.refetch()} />
      ) : (
        <>
          <section aria-labelledby="own-heading">
            <h2 id="own-heading" className="mb-2 text-sm font-semibold text-ink">
              Yours
            </h2>
            {own.length === 0 ? (
              <p className="rounded-card border border-dashed border-line bg-surface-2 px-4 py-5 text-[13px] text-ink-secondary">
                You have no categories of your own yet. Add one, or import a file that has its own
                Category column and the new names appear here.
              </p>
            ) : (
              <ul
                aria-label="Your categories"
                className="divide-y divide-line overflow-hidden rounded-card border border-line bg-surface"
              >
                {own.map((c) => (
                  <li key={c.name} className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3">
                    <div className="min-w-[10rem] flex-1">
                      <p className="break-words text-[14px] font-medium text-ink">{c.name}</p>
                      <p className="text-[12px] text-ink-secondary">{usage(c.transaction_count)}</p>
                    </div>
                    <div className="flex gap-1">
                      <Button
                        variant="secondary"
                        size="sm"
                        aria-label={`Rename ${c.name}`}
                        onClick={() => setDialogue({ kind: "rename", category: c })}
                      >
                        Rename
                      </Button>
                      <Button
                        variant="secondary"
                        size="sm"
                        aria-label={`Delete ${c.name}`}
                        onClick={() => setDialogue({ kind: "delete", category: c })}
                      >
                        Delete
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section aria-labelledby="builtin-heading">
            <h2 id="builtin-heading" className="mb-2 text-sm font-semibold text-ink">
              Built in
            </h2>
            <ul
              aria-label="Built-in categories"
              className="divide-y divide-line overflow-hidden rounded-card border border-line bg-surface"
            >
              {builtIn.map((c) => (
                <li key={c.name} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3">
                  <div className="min-w-[10rem] flex-1">
                    <p className="text-[14px] font-medium text-ink">{c.name}</p>
                    <p className="text-[12px] text-ink-secondary">
                      {c.note ? `${c.note} ` : ""}
                      {usage(c.transaction_count)}
                    </p>
                  </div>
                  <span className="rounded-full bg-surface-2 px-2.5 py-0.5 text-[11px] font-medium text-ink-secondary">
                    Fixed
                  </span>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}

      <Dialog
        open={dialogue?.kind === "add"}
        title="Add a category"
        onClose={close}
        dismissible={!add.isPending}
      >
        {dialogue?.kind === "add" && (
          <NameForm
            label="Name"
            submitLabel="Add category"
            reason="Type a name for the category."
            initial=""
            pending={add.isPending}
            error={add.error?.message ?? null}
            onCancel={close}
            onSubmit={(name) => add.mutate(name, { onSuccess: close })}
          />
        )}
      </Dialog>

      <Dialog
        open={dialogue?.kind === "rename"}
        title="Rename category"
        onClose={close}
        dismissible={!rename.isPending}
      >
        {dialogue?.kind === "rename" && (
          <NameForm
            label="New name"
            submitLabel="Save name"
            reason="Type a different name."
            initial={dialogue.category.name}
            pending={rename.isPending}
            error={rename.error?.message ?? null}
            note={`Every transaction in ${dialogue.category.name} (${usage(dialogue.category.transaction_count).toLowerCase()}) moves to the new name.`}
            onCancel={close}
            onSubmit={(newName) =>
              rename.mutate(
                { name: dialogue.category.name, newName },
                { onSuccess: closeAndFocusHeading },
              )
            }
          />
        )}
      </Dialog>

      <Dialog
        open={dialogue?.kind === "delete"}
        title="Delete category"
        onClose={close}
        dismissible={!remove.isPending}
      >
        {dialogue?.kind === "delete" && (
          <DeleteForm
            category={dialogue.category}
targets={categories.filter(
              (c) =>
                c.assignable &&
                c.name !== dialogue.category.name &&
                !MOVE_NOT_ALLOWED.has(c.name),
            )}
            pending={remove.isPending}
            error={remove.error?.message ?? null}
            onCancel={close}
            onDelete={(moveTo) =>
              remove.mutate(
                { name: dialogue.category.name, moveTo },
                { onSuccess: closeAndFocusHeading },
              )
            }
          />
        )}
      </Dialog>
    </div>
  );
}

type NameFormProps = {
  label: string;
  submitLabel: string;
  reason: string;
  initial: string;
  note?: string;
  pending: boolean;
  error: string | null;
  onCancel: () => void;
  onSubmit: (name: string) => void;
};

function NameForm({
  label,
  submitLabel,
  reason,
  initial,
  note,
  pending,
  error,
  onCancel,
  onSubmit,
}: NameFormProps) {
  const [name, setName] = useState(initial);
  const trimmed = name.trim();
  const valid = trimmed !== "" && trimmed !== initial;
  return (
    <form
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault();
        if (valid) onSubmit(trimmed);
      }}
    >
      <TextField
        label={label}
        maxLength={40}
        value={name}
        data-autofocus
        onChange={(event) => setName(event.target.value)}
      />
      {note && <p className="text-[12px] text-ink-secondary">{note}</p>}
      {error && (
        <Banner tone="danger" title="Not saved">
          {error}
        </Banner>
      )}
      {!valid && (
        <p id="category-reason" className="text-[12px] text-ink-secondary">
          {reason}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onCancel} disabled={pending}>
          Cancel
        </Button>
        <Button
          type="submit"
          variant="accent"
          disabled={!valid || pending}
          aria-describedby={valid ? undefined : "category-reason"}
        >
          {pending ? "Saving…" : submitLabel}
        </Button>
      </div>
    </form>
  );
}

type DeleteFormProps = {
  category: Category;
  targets: readonly Category[];
  pending: boolean;
  error: string | null;
  onCancel: () => void;
  onDelete: (moveTo: string | undefined) => void;
};

function DeleteForm({ category, targets, pending, error, onCancel, onDelete }: DeleteFormProps) {
  const [moveTo, setMoveTo] = useState("");
  const used = category.transaction_count > 0;
  const ready = !used || moveTo !== "";
  return (
    <div className="space-y-4">
      {used ? (
        <div className="flex flex-col gap-1.5">
          <label htmlFor="move-to" className="text-xs font-medium text-ink-secondary">
            Move its {plural(category.transaction_count, "transaction")} to
          </label>
          <select
            id="move-to"
            value={moveTo}
            onChange={(event) => setMoveTo(event.target.value)}
            className="h-10 rounded-lg border border-field bg-surface px-3 text-[14px] text-ink"
          >
            <option value="">Choose a category…</option>
            {targets.map((c) => (
              <option key={c.name} value={c.name}>
                {c.name}
              </option>
            ))}
          </select>
          <p className="text-[12px] text-ink-secondary">
            {category.name} is then deleted. Moving into another of your categories merges the two.
          </p>
        </div>
      ) : (
        <p className="text-[13px] text-ink-secondary">
          Delete {category.name}? No transaction uses it.
        </p>
      )}
      {error && (
        <Banner tone="danger" title="Not deleted">
          {error}
        </Banner>
      )}
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onCancel} disabled={pending}>
          Keep it
        </Button>
        <Button
          variant="danger"
          disabled={!ready || pending}
          onClick={() => onDelete(used ? moveTo : undefined)}
        >
          {pending ? "Deleting…" : "Delete"}
        </Button>
      </div>
    </div>
  );
}
