"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { api } from "@/lib/api/client";
import { useAuth } from "@/lib/session";

type Props = { children: ReactNode };

/**
 * Renders its children only for a signed-in visitor. A stored session is also confirmed with the
 * server once; if the server rejects it, the API client clears it and the visitor lands on /login.
 * Whenever the session ends, cached query data is dropped so the next user never sees it.
 */
export function AuthGate({ children }: Props) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const auth = useAuth();

  useQuery({
    queryKey: ["me", auth.session?.token],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/auth/me");
      if (error) throw error;
      return data ?? null;
    },
    enabled: auth.status === "authenticated",
    retry: false,
    staleTime: 5 * 60_000,
  });

  useEffect(() => {
    if (auth.status === "anonymous") {
      queryClient.clear();
      router.replace("/login");
    }
  }, [auth.status, queryClient, router]);

  if (auth.status !== "authenticated") {
    return (
      <div role="status" className="flex min-h-dvh items-center justify-center text-sm text-ink-secondary">
        Loading…
      </div>
    );
  }
  return <>{children}</>;
}
