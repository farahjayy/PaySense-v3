"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { AssistantPanel } from "@/components/assistant/AssistantPanel";
import { Button } from "@/components/ui/Button";
import { isActive } from "@/lib/nav";
import { api } from "@/lib/api/client";
import { clearSession, type Session } from "@/lib/session";

type NavItem = { href: string; label: string; icon: string; mobile: boolean };

// `mobile` marks the five items that fit a phone's bottom bar; the rest are in the sidebar and, on
// a phone, in the "More pages" row under the header.
const NAV_ITEMS: readonly NavItem[] = [
  { href: "/", label: "Dashboard", icon: "◫", mobile: true },
  { href: "/transactions", label: "Transactions", icon: "≡", mobile: true },
  { href: "/categories", label: "Categories", icon: "#", mobile: false },
  { href: "/recurring", label: "Recurring", icon: "↻", mobile: false },
  { href: "/plans", label: "Plans", icon: "▤", mobile: true },
  { href: "/risk", label: "Risk check", icon: "◔", mobile: true },
  { href: "/import", label: "Import", icon: "⇪", mobile: true },
  { href: "/model", label: "About the model", icon: "ⓘ", mobile: false },
];

function navLinkClass(active: boolean): string {
  return active
    ? "bg-accent-bg font-semibold text-accent"
    : "text-ink-secondary hover:bg-surface-2 hover:text-ink";
}

function Sidebar({ pathname }: { pathname: string }) {
  return (
    <aside className="sticky top-0 hidden h-screen w-56 shrink-0 flex-col border-r border-line bg-surface px-4 py-6 md:flex">
      <Link href="/" className="mb-8 block px-2 text-lg font-bold tracking-tight text-ink">
        Pay<span className="text-accent">Sense</span>
      </Link>
      <nav aria-label="Main navigation" className="flex flex-col gap-1">
        {NAV_ITEMS.map((item) => {
          const active = isActive(pathname, item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium transition-colors ${navLinkClass(active)}`}
            >
              <span aria-hidden className="text-sm">
                {item.icon}
              </span>
              {item.label}
            </Link>
          );
        })}
      </nav>
      <p className="mt-auto px-2 text-[10px] leading-relaxed text-ink-muted">
        Financial health forecasting and BNPL risk classification for students.
      </p>
    </aside>
  );
}

function MobileNav({ pathname }: { pathname: string }) {
  return (
    <nav
      aria-label="Quick navigation"
      className="fixed inset-x-0 bottom-0 z-40 flex border-t border-line bg-surface md:hidden"
    >
      {NAV_ITEMS.filter((item) => item.mobile).map((item) => {
        const active = isActive(pathname, item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={`flex flex-1 flex-col items-center gap-0.5 py-2 text-[10px] font-medium ${
              active ? "text-accent" : "text-ink-muted"
            }`}
          >
            <span aria-hidden className="text-base leading-none">
              {item.icon}
            </span>
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

type Props = { user: Session["user"]; children: ReactNode };

export function AppShell({ user, children }: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const main = useRef<HTMLElement>(null);
  const firstRender = useRef(true);
  const askButton = useRef<HTMLButtonElement>(null);
  const [assistantOpen, setAssistantOpen] = useState(false);

  function closeAssistant() {
    setAssistantOpen(false);
    askButton.current?.focus(); // back to where the person was
  }

  // After navigating, move focus to the new page so keyboard and screen-reader users start at its
  // top instead of wherever the old page left them. Not on the first load.
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    // The page's own heading, so a screen reader announces where it landed; main as a fallback.
    (main.current?.querySelector<HTMLElement>("h1") ?? main.current)?.focus();
  }, [pathname]);

  function handleLogout() {
    // Revoke on the server (every session of this user ends, D-49); the page does not wait for
    // it, and a failure still logs out locally.
    api.POST("/api/auth/logout").catch(() => undefined);
    clearSession();
    queryClient.clear();
    router.replace("/login");
  }

  return (
    <div className="flex min-h-screen">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-lg focus:bg-ink focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-white"
      >
        Skip to content
      </a>
      <Sidebar pathname={pathname} />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center justify-between gap-3 border-b border-line bg-surface px-4 sm:px-6">
          <Link href="/" className="text-base font-bold tracking-tight text-ink md:hidden">
            Pay<span className="text-accent">Sense</span>
          </Link>
          <div className="ml-auto flex items-center gap-3">
            <Button
              ref={askButton}
              variant="accent"
              size="sm"
              aria-expanded={assistantOpen}
              onClick={() => (assistantOpen ? closeAssistant() : setAssistantOpen(true))}
            >
              Ask PaySense
            </Button>
            <span className="max-w-[10rem] truncate text-[13px] font-medium text-ink">
              {user.display_name}
            </span>
            <Button variant="secondary" size="sm" onClick={handleLogout}>
              Log out
            </Button>
          </div>
        </header>
        <nav
          aria-label="More pages"
          className="flex gap-5 border-b border-line bg-surface px-4 py-2 text-[13px] font-medium md:hidden"
        >
          {NAV_ITEMS.filter((item) => !item.mobile).map((item) => (
            <Link
              key={item.href}
              href={item.href}
              aria-current={isActive(pathname, item.href) ? "page" : undefined}
              className="py-1 text-accent underline-offset-2 hover:underline"
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <main
          id="main"
          ref={main}
          tabIndex={-1}
          className="flex-1 px-4 py-6 pb-24 outline-none sm:px-6 md:pb-8"
        >
          {children}
        </main>
      </div>
      <MobileNav pathname={pathname} />
      {assistantOpen && <AssistantPanel onClose={closeAssistant} />}
    </div>
  );
}
