"use client";

import { useId, useState, type FormEvent, type ReactNode } from "react";

import { Button } from "@/components/ui/Button";
import { useProviders } from "@/lib/api/queries";
import {
  QUICK_ACTIONS,
  addTransactionArgs,
  budgetArgs,
  checkPurchaseArgs,
  MAX_PASTE_CHARS,
  type TransactionForm,
} from "@/lib/assistant";
import { todayIso } from "@/lib/format";

/** Runs one Tier 0/1 tool. `label` is what the person pressed, shown as their turn in the chat. */
export type RunTool = (
  tool: string,
  args: Record<string, unknown>,
  pastedText?: string,
  label?: string,
) => void;

const INPUT =
  "h-9 w-full rounded-lg border border-line bg-surface px-2.5 text-[13px] text-ink focus:border-accent focus:outline-none";

function Field({ label, children }: { label: string; children: (id: string) => ReactNode }) {
  const id = useId();
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-[12px] font-medium text-ink-secondary">
        {label}
      </label>
      {children(id)}
    </div>
  );
}

type FormName = "purchase" | "budget" | "transaction" | "paste" | null;

/**
 * Guided mode (D-47): the same tools from buttons and small forms, with no model. Proposals made
 * here still need Confirm, exactly as in a chat.
 */
export function GuidedActions({ onRun, busy }: { onRun: RunTool; busy: boolean }) {
  const [open, setOpen] = useState<FormName>(null);
  const toggle = (name: FormName) => setOpen((current) => (current === name ? null : name));
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Quick actions">
        {QUICK_ACTIONS.map((q) => (
          <Button
            key={q.tool}
            size="sm"
            variant="secondary"
            disabled={busy}
            onClick={() => onRun(q.tool, {}, undefined, q.label)}
          >
            {q.label}
          </Button>
        ))}
      </div>
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Forms">
        <Button
          size="sm"
          variant="secondary"
          aria-expanded={open === "purchase"}
          onClick={() => toggle("purchase")}
        >
          Check a purchase
        </Button>
        <Button
          size="sm"
          variant="secondary"
          aria-expanded={open === "budget"}
          onClick={() => toggle("budget")}
        >
          Set a budget
        </Button>
        <Button
          size="sm"
          variant="secondary"
          aria-expanded={open === "transaction"}
          onClick={() => toggle("transaction")}
        >
          Add a transaction
        </Button>
        <Button
          size="sm"
          variant="secondary"
          aria-expanded={open === "paste"}
          onClick={() => toggle("paste")}
        >
          Paste transactions
        </Button>
      </div>
      {open === "purchase" && <PurchaseForm onRun={onRun} busy={busy} />}
      {open === "budget" && <BudgetForm onRun={onRun} busy={busy} />}
      {open === "transaction" && <TransactionFormView onRun={onRun} busy={busy} />}
      {open === "paste" && <PasteForm onRun={onRun} busy={busy} />}
    </div>
  );
}

type FormProps = { onRun: RunTool; busy: boolean };

function FormBox({
  label,
  onSubmit,
  children,
}: {
  label: string;
  onSubmit: (e: FormEvent) => void;
  children: ReactNode;
}) {
  return (
    <form
      aria-label={label}
      onSubmit={onSubmit}
      className="space-y-2.5 rounded-card border border-line bg-surface p-3"
    >
      {children}
    </form>
  );
}

function PurchaseForm({ onRun, busy }: FormProps) {
  const providers = useProviders();
  const [form, setForm] = useState({
    item: "",
    price: "",
    provider: "spaylater",
    instalments: "3",
  });
  const args = checkPurchaseArgs(form, todayIso());
  return (
    <FormBox
      label="Check a purchase"
      onSubmit={(e) => {
        e.preventDefault();
        if (args) onRun("check_purchase_risk", args, undefined, "Check a purchase");
      }}
    >
      <Field label="What are you buying?">
        {(id) => (
          <input
            id={id}
            className={INPUT}
            value={form.item}
            onChange={(e) => setForm({ ...form, item: e.target.value })}
          />
        )}
      </Field>
      <div className="grid grid-cols-2 gap-2">
        <Field label="Price (RM)">
          {(id) => (
            <input
              id={id}
              inputMode="decimal"
              className={INPUT}
              value={form.price}
              onChange={(e) => setForm({ ...form, price: e.target.value })}
            />
          )}
        </Field>
        <Field label="Instalments">
          {(id) => (
            <input
              id={id}
              inputMode="numeric"
              className={INPUT}
              value={form.instalments}
              onChange={(e) => setForm({ ...form, instalments: e.target.value })}
            />
          )}
        </Field>
      </div>
      <Field label="Provider">
        {(id) => (
          <select
            id={id}
            className={INPUT}
            value={form.provider}
            onChange={(e) => setForm({ ...form, provider: e.target.value })}
          >
            {(providers.data ?? []).map((p) => (
              <option key={p.key} value={p.key}>
                {p.label}
              </option>
            ))}
            {!providers.data && <option value="spaylater">SPayLater</option>}
          </select>
        )}
      </Field>
      <Button type="submit" size="sm" variant="accent" disabled={!args || busy}>
        Check it
      </Button>
    </FormBox>
  );
}

function BudgetForm({ onRun, busy }: FormProps) {
  const [form, setForm] = useState({ category: "", limit: "" });
  const args = budgetArgs(form);
  return (
    <FormBox
      label="Set a budget"
      onSubmit={(e) => {
        e.preventDefault();
        if (args) onRun("propose_action", args, undefined, "Set a budget");
      }}
    >
      <div className="grid grid-cols-2 gap-2">
        <Field label="Category">
          {(id) => (
            <input
              id={id}
              className={INPUT}
              value={form.category}
              onChange={(e) => setForm({ ...form, category: e.target.value })}
            />
          )}
        </Field>
        <Field label="Monthly limit (RM)">
          {(id) => (
            <input
              id={id}
              inputMode="decimal"
              className={INPUT}
              value={form.limit}
              onChange={(e) => setForm({ ...form, limit: e.target.value })}
            />
          )}
        </Field>
      </div>
      <Button type="submit" size="sm" variant="accent" disabled={!args || busy}>
        Propose this budget
      </Button>
    </FormBox>
  );
}

function TransactionFormView({ onRun, busy }: FormProps) {
  const [form, setForm] = useState<TransactionForm>({
    amount: "",
    type: "expense",
    category: "",
    description: "",
  });
  const args = addTransactionArgs(form, todayIso());
  return (
    <FormBox
      label="Add a transaction"
      onSubmit={(e) => {
        e.preventDefault();
        if (args) onRun("propose_action", args, undefined, "Add a transaction");
      }}
    >
      <div className="grid grid-cols-2 gap-2">
        <Field label="Amount (RM)">
          {(id) => (
            <input
              id={id}
              inputMode="decimal"
              className={INPUT}
              value={form.amount}
              onChange={(e) => setForm({ ...form, amount: e.target.value })}
            />
          )}
        </Field>
        <Field label="Type">
          {(id) => (
            <select
              id={id}
              className={INPUT}
              value={form.type}
              onChange={(e) =>
                setForm({
                  ...form,
                  type: e.target.value as TransactionForm["type"],
                })
              }
            >
              <option value="expense">Expense</option>
              <option value="income">Income</option>
              <option value="savings">Savings</option>
            </select>
          )}
        </Field>
      </div>
      <Field label="Category">
        {(id) => (
          <input
            id={id}
            className={INPUT}
            value={form.category}
            onChange={(e) => setForm({ ...form, category: e.target.value })}
          />
        )}
      </Field>
      <Field label="Description (optional)">
        {(id) => (
          <input
            id={id}
            className={INPUT}
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
        )}
      </Field>
      <Button type="submit" size="sm" variant="accent" disabled={!args || busy}>
        Propose this transaction
      </Button>
    </FormBox>
  );
}

function PasteForm({ onRun, busy }: FormProps) {
  const [text, setText] = useState("");
  return (
    <FormBox
      label="Paste transactions"
      onSubmit={(e) => {
        e.preventDefault();
        if (text.trim()) onRun("parse_pasted_transactions", {}, text, "Paste transactions");
      }}
    >
      <Field label="A statement with Date, Description and Amount columns">
        {(id) => (
          <textarea
            id={id}
            rows={4}
            maxLength={MAX_PASTE_CHARS}
            className="w-full rounded-lg border border-line bg-surface p-2 font-mono text-[12px] text-ink focus:border-accent focus:outline-none"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        )}
      </Field>
      <Button type="submit" size="sm" variant="accent" disabled={!text.trim() || busy}>
        Read it
      </Button>
    </FormBox>
  );
}
