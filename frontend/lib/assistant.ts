/**
 * Pure helpers for the assistant panel (WP5, ADRs D-47, D-48). No money arithmetic: amounts arrive
 * as integer sen and are only formatted; typed ringgit becomes sen through `parseRm`.
 */
import type { components } from "@/lib/api/schema";
import { ApiError } from "@/lib/api/queries";
import { formatDate, formatPercent } from "@/lib/format";
import { formatRm, parseRm } from "@/lib/money";

type Schemas = components["schemas"];
export type ChatReply = Schemas["ChatOut"];
export type ChatCard = ChatReply["cards"][number];
export type PendingAction = ChatReply["pending_actions"][number];
export type Step = Schemas["StepOut"];
export type ActionResult = Schemas["ActionResultOut"];
export type AssistantStatus = Schemas["AssistantStatusOut"];
export type SourceFigure = Schemas["SourceFigureOut"];
export type ChatTurn = Schemas["ChatTurnIn"];
export type ActionType = PendingAction["type"];

/** How many earlier turns go with a message, and how long each may be (the server's limits). */
export const HISTORY_TURNS = 8;
export const MAX_TURN_CHARS = 4000;
export const MAX_MESSAGE_CHARS = 2000;
export const MAX_PASTE_CHARS = 8000;

export const TIER_LABEL: Record<0 | 1 | 2, string> = {
  0: "Read",
  1: "Worked out",
  2: "Needs your OK",
};

export const STATUS_LABEL: Record<Step["status"], string> = {
  ok: "Done",
  refused: "Refused",
  error: "Did not work",
};

const ACTION_TITLES: Record<ActionType, string> = {
  add_transaction: "Add this transaction?",
  confirm_import: "Add these transactions?",
  create_plan: "Add this BNPL plan?",
  set_budget: "Save this budget?",
  delete_budget: "Remove this budget?",
};

export function actionTitle(type: ActionType): string {
  return ACTION_TITLES[type];
}

/** "check_purchase_risk" -> "Check purchase risk". */
export function toolLabel(tool: string): string {
  const words = tool.replace(/_/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** The last few turns as plain text only: tool results are never sent back (D-47). */
export function trimHistory(turns: readonly ChatTurn[]): ChatTurn[] {
  return turns
    .filter((t) => t.text.trim() !== "")
    .slice(-HISTORY_TURNS)
    .map((t) => ({ role: t.role, text: t.text.slice(0, MAX_TURN_CHARS) }));
}

function fieldLabel(key: string): string {
  return toolLabel(key.replace(/_sen$/, ""));
}

/** A tool call's inputs as short lines for the "What I did" list. */
export function describeInputs(inputs: Record<string, unknown>): string[] {
  return Object.entries(inputs).map(([key, value]) => {
    let shown: string;
    if (key.endsWith("_sen") && typeof value === "number" && Number.isSafeInteger(value)) {
      shown = formatRm(value);
    } else if (Array.isArray(value)) {
      shown = `${value.length} ${value.length === 1 ? "item" : "items"}`;
    } else if (typeof value === "object" && value !== null) {
      shown = JSON.stringify(value);
    } else {
      shown = String(value);
    }
    return `${fieldLabel(key)}: ${shown}`;
  });
}

/** A recommendation's source figure, written the way the server wrote it into the sentence. */
export function formatSource(source: SourceFigure): string {
  const { value, unit } = source;
  if (unit === "sen" && typeof value === "number") return formatRm(value);
  if ((unit === "probability" || unit === "percent") && typeof value === "number") {
    return formatPercent(value);
  }
  if (unit === "date" && typeof value === "string") return formatDate(value.slice(0, 10));
  return String(value);
}

export type PanelState = "consent" | "budget" | "rate_limited" | "offline" | "error";

export function stateFromError(error: unknown): PanelState {
  if (!(error instanceof ApiError)) return "error";
  if (error.code === "consent_required") return "consent";
  if (error.code === "assistant_daily_budget") return "budget";
  if (error.status === 429) return "rate_limited";
  if (error.code === "network_error") return "offline";
  return "error";
}

/** The demo story (work-packages.md section 6), offered as one-tap prompts. */
export const SUGGESTED_PROMPTS = [
  "Can I afford an RM799 phone on SPayLater over 3 months?",
  "What's the safest way to buy it?",
  "What do I owe this month?",
  "How am I doing?",
  "Set my food budget to RM400.",
  "Suggest a budget.",
] as const;

/** Guided mode: read and compute tools a button can run with no model (Tier 0/1 only). */
export const QUICK_ACTIONS = [
  { tool: "get_alerts", label: "What needs attention" },
  { tool: "get_forecast", label: "My forecast" },
  { tool: "get_bill_analysis", label: "What I owe" },
  { tool: "get_spending_insights", label: "How am I doing" },
  { tool: "get_budget_status", label: "My budgets" },
  { tool: "suggest_budget", label: "Suggest a budget" },
] as const;

export type PurchaseForm = {
  item: string;
  price: string;
  provider: string;
  instalments: string;
};

/** Arguments for `check_purchase_risk`, or null while the form is incomplete or ambiguous. */
export function checkPurchaseArgs(form: PurchaseForm, today: string) {
  const item = form.item.trim();
  const sen = parseRm(form.price);
  const count = /^\d{1,2}$/.test(form.instalments.trim()) ? Number(form.instalments) : 0;
  if (!item || sen === null || sen <= 0 || count < 1 || !form.provider) return null;
  return {
    provider: form.provider,
    item_name: item,
    purchase_date: today,
    num_installments: count,
    total_price_sen: sen,
  };
}

export type BudgetForm = { category: string; limit: string };

export function budgetArgs(form: BudgetForm) {
  const category = form.category.trim();
  const sen = parseRm(form.limit);
  if (!category || sen === null || sen <= 0) return null;
  return { type: "set_budget" as const, payload: { category, limit_sen: sen } };
}

export type TransactionForm = {
  amount: string;
  type: "income" | "expense" | "savings";
  category: string;
  description: string;
};

export function addTransactionArgs(form: TransactionForm, today: string) {
  const sen = parseRm(form.amount);
  const category = form.category.trim();
  if (sen === null || sen <= 0 || !category) return null;
  const description = form.description.trim();
  return {
    type: "add_transaction" as const,
    payload: {
      date: today,
      amount_sen: sen,
      type: form.type,
      category,
      ...(description ? { description } : {}),
    },
  };
}
