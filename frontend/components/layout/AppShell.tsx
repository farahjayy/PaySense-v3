"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/Button";
import { isActive } from "@/lib/nav";
import { clearSession, type Session } from "@/lib/session";

type NavItem = { href: string; label: string; icon: string };

// Grows with each phase: screens are added here as their backend lands.
const NAV_ITEMS: readonly NavItem[] = [{ href: "/", label: "Dashboard", icon: "◫" }];

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
      aria-label="Main navigation"
      className="fixed inset-x-0 bottom-0 z-40 flex border-t border-line bg-surface md:hidden"
    >
      {NAV_ITEMS.map((item) => {
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

  function handleLogout() {
    clearSession();
    queryClient.clear();
    router.replace("/login");
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar pathname={pathname} />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center justify-between gap-3 border-b border-line bg-surface px-4 sm:px-6">
          <Link href="/" className="text-base font-bold tracking-tight text-ink md:hidden">
            Pay<span className="text-accent">Sense</span>
          </Link>
          <div className="ml-auto flex items-center gap-3">
            <span className="max-w-[10rem] truncate text-[13px] font-medium text-ink">
              {user.display_name}
            </span>
            <Button variant="secondary" size="sm" onClick={handleLogout}>
              Log out
            </Button>
          </div>
        </header>
        <main className="flex-1 px-4 py-6 pb-24 sm:px-6 md:pb-8">{children}</main>
      </div>
      <MobileNav pathname={pathname} />
    </div>
  );
}
