/**
 * Hooks for the Topic A screens (budgets, insights, recommendations, alerts) and the account page
 * (consent, export, delete). Same rules as `queries.ts`: types only from the generated schema,
 * no money arithmetic, server sentences for errors.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import { unwrap } from "./queries";
import type { components } from "./schema";

type Schemas = components["schemas"];
export type Budget = Schemas["BudgetOut"];
export type BudgetStatus = Schemas["BudgetStatusOut"];
export type BudgetStatusItem = Schemas["BudgetStatusItemOut"];
export type BudgetSuggestion = Schemas["BudgetSuggestionOut"];
export type BillAnalysis = Schemas["BillAnalysisOut"];
export type SpendingInsights = Schemas["SpendingInsightsOut"];
export type Recommendation = Schemas["RecommendationOut"];
export type RecommendationList = Schemas["RecommendationListOut"];
export type Consent = Schemas["ConsentOut"];
export type AccountExport = Schemas["AccountExportOut"];

export const topicKeys = {
  budgets: ["budgets"] as const,
  budgetStatus: (month: string | null) => ["budgets", "status", month ?? "current"] as const,
  billAnalysis: ["insights", "bills"] as const,
  spending: (month: string) => ["insights", "spending", month] as const,
  recommendations: ["recommendations"] as const,
  alerts: ["alerts"] as const,
  consent: ["consent"] as const,
};

export function useBudgets() {
  return useQuery({
    queryKey: topicKeys.budgets,
    queryFn: async () => unwrap(api.GET("/api/budgets")),
  });
}

/** Budgets against a month's spending; without a month, the server's current month (Malaysia). */
export function useBudgetStatus(month: string | null = null) {
  return useQuery({
    queryKey: topicKeys.budgetStatus(month),
    queryFn: async () =>
      unwrap(api.GET("/api/budgets/status", { params: { query: month ? { month } : {} } })),
  });
}

/** Budgets, their status, recommendations and alerts all move when a budget changes. */
function useInvalidateBudgets() {
  const client = useQueryClient();
  return () =>
    Promise.all(
      ["budgets", "recommendations", "alerts"].map((key) =>
        client.invalidateQueries({ queryKey: [key] }),
      ),
    );
}

export function useSetBudget() {
  const invalidate = useInvalidateBudgets();
  return useMutation({
    mutationFn: async (body: Schemas["BudgetIn"]) => unwrap(api.PUT("/api/budgets", { body })),
    onSuccess: () => void invalidate(),
  });
}

export function useDeleteBudget() {
  const invalidate = useInvalidateBudgets();
  return useMutation({
    mutationFn: async (category: string) =>
      unwrap(api.DELETE("/api/budgets", { params: { query: { category } } })),
    onSuccess: () => void invalidate(),
  });
}

export function useSuggestBudget() {
  return useMutation({
    mutationFn: async (month?: string) =>
      unwrap(api.POST("/api/budgets/suggest", { body: month ? { month } : {} })),
  });
}

export function useBillAnalysis() {
  return useQuery({
    queryKey: topicKeys.billAnalysis,
    queryFn: async () => unwrap(api.GET("/api/insights/bills")),
  });
}

export function useSpendingInsights(month: string | null) {
  return useQuery({
    queryKey: topicKeys.spending(month ?? ""),
    queryFn: async () =>
      unwrap(api.GET("/api/insights/spending", { params: { query: { month: month ?? "" } } })),
    enabled: month !== null,
  });
}

export function useRecommendations() {
  return useQuery({
    queryKey: topicKeys.recommendations,
    queryFn: async () => unwrap(api.GET("/api/recommendations")),
  });
}

export function useAlerts() {
  return useQuery({
    queryKey: topicKeys.alerts,
    queryFn: async () => unwrap(api.GET("/api/alerts")),
  });
}

export function useConsent() {
  return useQuery({
    queryKey: topicKeys.consent,
    queryFn: async () => unwrap(api.GET("/api/account/consent")),
  });
}

export function useAcceptConsent() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (version: string) =>
      unwrap(api.POST("/api/account/consent", { body: { version } })),
    onSuccess: (data) => client.setQueryData(topicKeys.consent, data),
  });
}

export function useExportData() {
  return useMutation({
    mutationFn: async () => unwrap(api.POST("/api/account/export")),
  });
}

export function useDeleteData() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (passphrase: string) =>
      unwrap(
        api.POST("/api/account/delete", {
          body: { confirmation: "delete my data", passphrase },
        }),
      ),
    onSuccess: () => client.invalidateQueries(),
  });
}
