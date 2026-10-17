/**
 * Data hooks for the assistant (WP5). The panel keeps the conversation itself; these only call the
 * API. A confirmed proposal changed the ledger, so every screen's data is refreshed afterwards.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { components } from "./schema";
import { api } from "./client";
import { unwrap, useInvalidateLedger } from "./queries";

type Schemas = components["schemas"];
export type ChatRequest = Schemas["ChatIn"];
export type RunRequest = Schemas["RunToolIn"];

export const assistantKeys = {
  status: ["assistant", "status"] as const,
  opening: ["assistant", "opening"] as const,
};

/** Screens added for budgets, insights and recommendations (WP3) read these keys. */
const TOPIC_KEYS = ["budgets", "insights", "recommendations", "alerts", "assistant"];

export function useAssistantStatus() {
  return useQuery({
    queryKey: assistantKeys.status,
    queryFn: async () => unwrap(api.GET("/api/assistant/status")),
  });
}

/** The first turn: what needs attention now. No model is called for it. */
export function useAssistantOpening(enabled: boolean) {
  return useQuery({
    queryKey: assistantKeys.opening,
    queryFn: async () => unwrap(api.GET("/api/assistant/opening")),
    enabled,
    staleTime: 60_000,
  });
}

export function useAssistantChat() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (body: ChatRequest) => unwrap(api.POST("/api/assistant/chat", { body })),
    onSettled: () => client.invalidateQueries({ queryKey: assistantKeys.status }),
  });
}

export function useAssistantRun() {
  return useMutation({
    mutationFn: async (body: RunRequest) => unwrap(api.POST("/api/assistant/run", { body })),
  });
}

function useRefreshAfterWrite() {
  const ledger = useInvalidateLedger();
  const client = useQueryClient();
  return () =>
    Promise.all([
      ledger(),
      ...TOPIC_KEYS.map((key) => client.invalidateQueries({ queryKey: [key] })),
    ]);
}

export function useConfirmAction() {
  const refresh = useRefreshAfterWrite();
  return useMutation({
    mutationFn: async (id: string) =>
      unwrap(
        api.POST("/api/assistant/actions/{action_id}/confirm", {
          params: { path: { action_id: id } },
        }),
      ),
    onSuccess: () => {
      void refresh();
    },
  });
}

export function useDeclineAction() {
  return useMutation({
    mutationFn: async (id: string) =>
      unwrap(
        api.POST("/api/assistant/actions/{action_id}/decline", {
          params: { path: { action_id: id } },
        }),
      ),
  });
}
