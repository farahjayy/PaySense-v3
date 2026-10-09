/**
 * Typed data hooks over the generated client. Every screen reads the API through these, so
 * loading, error and refetch behaviour is the same everywhere and the types come only from the
 * backend's OpenAPI document. No money is computed here: amounts are integer sen as received.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import { errorMessage } from "./errors";
import type { components } from "./schema";

type Schemas = components["schemas"];
export type Forecast = Schemas["ForecastOut"];
export type MonthSummary = Schemas["MonthSummaryOut"];
export type Bills = Schemas["BillsOut"];
export type Suggestion = Schemas["SuggestionOut"];
export type RecurringItem = Schemas["RecurringOut"];
export type RecurringInput = Schemas["RecurringIn"];
export type Transaction = Schemas["TransactionOut"];
export type TransactionInput = Schemas["TransactionIn"];
export type Plan = Schemas["PlanOut"];
export type PlanInput = Schemas["PlanIn"];
export type PlanPreview = Schemas["PlanPreviewOut"];
export type ProviderInfo = Schemas["ProviderOut"];
export type ProviderLimit = Schemas["LimitOut"];
export type ImportPreview = Schemas["ImportPreviewOut"];
export type ConfirmRow = Schemas["ConfirmRow"];

/** A failed API call, with the server's own sentence when it sent one. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type Result<T> = { data?: T; error?: unknown; response: Response };

function codeOf(error: unknown): string | undefined {
  const detail = (error as { detail?: { code?: unknown } } | undefined)?.detail;
  return typeof detail?.code === "string" ? detail.code : undefined;
}

/** The data of a successful result; anything else becomes an ApiError. */
export function unwrap<T>(result: Result<T>): T {
  if (result.error !== undefined || result.data === undefined) {
    if (result.response.ok && result.response.status === 204) return undefined as T;
    throw new ApiError(errorMessage(result.error), result.response.status, codeOf(result.error));
  }
  return result.data;
}

export const queryKeys = {
  forecast: ["forecast"] as const,
  summary: ["summary"] as const,
  bills: ["bills"] as const,
  suggestions: ["suggestions"] as const,
  recurring: ["recurring"] as const,
  transactions: (filters: object) => ["transactions", filters] as const,
  plans: ["plans"] as const,
  providers: ["providers"] as const,
  limits: ["limits"] as const,
};

export function useForecast() {
  return useQuery({
    queryKey: queryKeys.forecast,
    queryFn: async () => unwrap(await api.GET("/api/forecast")),
  });
}

export function useMonthSummary() {
  return useQuery({
    queryKey: queryKeys.summary,
    queryFn: async () => unwrap(await api.GET("/api/summary/months")),
  });
}

export function useBills() {
  return useQuery({
    queryKey: queryKeys.bills,
    queryFn: async () => unwrap(await api.GET("/api/bills")),
  });
}

export function useSuggestions() {
  return useQuery({
    queryKey: queryKeys.suggestions,
    queryFn: async () => unwrap(await api.GET("/api/recurring-items/suggestions")),
  });
}

export function useRecurringItems() {
  return useQuery({
    queryKey: queryKeys.recurring,
    queryFn: async () => unwrap(await api.GET("/api/recurring-items")),
  });
}

export type TransactionFilters = {
  start?: string;
  end?: string;
  type?: "income" | "expense" | "savings";
  category?: string;
};

export function useTransactions(filters: TransactionFilters = {}) {
  return useQuery({
    queryKey: queryKeys.transactions(filters),
    queryFn: async () => unwrap(await api.GET("/api/transactions", { params: { query: filters } })),
  });
}

export function usePlans() {
  return useQuery({
    queryKey: queryKeys.plans,
    queryFn: async () => unwrap(await api.GET("/api/plans")),
  });
}

export function useProviders() {
  return useQuery({
    queryKey: queryKeys.providers,
    queryFn: async () => unwrap(await api.GET("/api/providers")),
    staleTime: Infinity, // provider rules do not change while the app is open
  });
}

export function useProviderLimits() {
  return useQuery({
    queryKey: queryKeys.limits,
    queryFn: async () => unwrap(await api.GET("/api/provider-limits")),
  });
}

/** What a change to the ledger makes stale: everything the forecast is built from. */
function useInvalidateLedger() {
  const client = useQueryClient();
  return () =>
    Promise.all(
      ["forecast", "summary", "bills", "suggestions", "recurring", "transactions", "plans"].map(
        (key) => client.invalidateQueries({ queryKey: [key] }),
      ),
    );
}

export function useImportPreview() {
  return useMutation({
    mutationFn: async (file: File) => {
      const body = new FormData();
      body.append("file", file);
      return unwrap(
        await api.POST("/api/import/csv", {
          body: body as unknown as { file: string },
          bodySerializer: (value) => value as unknown as FormData,
        }),
      );
    },
  });
}

export function useImportConfirm() {
  const invalidate = useInvalidateLedger();
  return useMutation({
    mutationFn: async (rows: ConfirmRow[]) =>
      unwrap(await api.POST("/api/import/confirm", { body: { rows } })),
    onSuccess: invalidate,
  });
}

export function useCreateTransaction() {
  const invalidate = useInvalidateLedger();
  return useMutation({
    mutationFn: async (body: TransactionInput) =>
      unwrap(await api.POST("/api/transactions", { body })),
    onSuccess: invalidate,
  });
}

export function useUpdateTransaction() {
  const invalidate = useInvalidateLedger();
  return useMutation({
    mutationFn: async ({ id, patch }: { id: string; patch: Schemas["TransactionPatch"] }) =>
      unwrap(
        await api.PATCH("/api/transactions/{transaction_id}", {
          params: { path: { transaction_id: id } },
          body: patch,
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useDeleteTransaction() {
  const invalidate = useInvalidateLedger();
  return useMutation({
    mutationFn: async (id: string) =>
      unwrap(
        await api.DELETE("/api/transactions/{transaction_id}", {
          params: { path: { transaction_id: id } },
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useCreateRecurring() {
  const invalidate = useInvalidateLedger();
  return useMutation({
    mutationFn: async (body: RecurringInput) =>
      unwrap(await api.POST("/api/recurring-items", { body })),
    onSuccess: invalidate,
  });
}

export function useUpdateRecurring() {
  const invalidate = useInvalidateLedger();
  return useMutation({
    mutationFn: async ({ id, patch }: { id: string; patch: Schemas["RecurringPatch"] }) =>
      unwrap(
        await api.PATCH("/api/recurring-items/{item_id}", {
          params: { path: { item_id: id } },
          body: patch,
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useDeleteRecurring() {
  const invalidate = useInvalidateLedger();
  return useMutation({
    mutationFn: async (id: string) =>
      unwrap(
        await api.DELETE("/api/recurring-items/{item_id}", { params: { path: { item_id: id } } }),
      ),
    onSuccess: invalidate,
  });
}

export function usePreviewPlan() {
  return useMutation({
    mutationFn: async (body: PlanInput) => unwrap(await api.POST("/api/plans/preview", { body })),
  });
}

export function useCreatePlan() {
  const invalidate = useInvalidateLedger();
  return useMutation({
    mutationFn: async (body: PlanInput) => unwrap(await api.POST("/api/plans", { body })),
    onSuccess: invalidate,
  });
}

export function usePayInstalment() {
  const invalidate = useInvalidateLedger();
  return useMutation({
    mutationFn: async ({
      planId,
      seq,
      paidDate,
    }: {
      planId: string;
      seq: number;
      paidDate?: string;
    }) =>
      unwrap(
        await api.POST("/api/plans/{plan_id}/installments/{seq}/pay", {
          params: { path: { plan_id: planId, seq } },
          body: paidDate ? { paid_date: paidDate } : {},
        }),
      ),
    onSuccess: invalidate,
  });
}

export function usePayInstalments() {
  const invalidate = useInvalidateLedger();
  return useMutation({
    mutationFn: async ({ planId, seqs }: { planId: string; seqs: number[] }) =>
      unwrap(
        await api.POST("/api/plans/{plan_id}/pay", {
          params: { path: { plan_id: planId } },
          body: { seqs },
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useDeletePlan() {
  const invalidate = useInvalidateLedger();
  return useMutation({
    mutationFn: async ({ id, keepPayments }: { id: string; keepPayments: boolean }) =>
      unwrap(
        await api.DELETE("/api/plans/{plan_id}", {
          params: { path: { plan_id: id }, query: { keep_payments: keepPayments } },
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useSetProviderLimit() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({ provider, limitSen }: { provider: string; limitSen: number }) =>
      unwrap(
        await api.PUT("/api/provider-limits/{provider}", {
          params: { path: { provider: provider as ProviderLimit["provider"] } },
          body: { limit_sen: limitSen },
        }),
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.limits }),
  });
}
