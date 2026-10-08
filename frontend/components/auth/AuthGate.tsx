"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { api } from "@/lib/api/client";
import { useAuth } from "@/lib/session";

type Props = { children: ReactNode };

/**
 * Renders its children only for a signed-in visitor. A stored session is also confirmed with the
 * server once; if the server rejects it, the API client clears it and the visitor lands on /login.
 */
export function AuthGate({ children }: Props) {
  const router = useRouter();
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
    if (auth.status === "anonymous") router.replace("/login");
  }, [auth.status, router]);

  if (auth.status !== "authenticated") {
    return (
      <div role="status" className="flex min-h-screen items-center justify-center text-sm text-ink-muted">
        Loading…
      </div>
    );
  }
  return <>{children}</>;
}
