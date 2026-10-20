"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Suspense,
  lazy,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  useSyncExternalStore,
  type ComponentProps,
  type ReactNode,
} from "react";

import { BrandMark } from "@/components/auth/LoginArt";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Tooltip } from "@/components/ui/Tooltip";
import { isActive } from "@/lib/nav";
import { api } from "@/lib/api/client";
import { AssistantLauncher } from "@/lib/assistantLauncher";
import { introSeen, markTourSeen, tourSeen, useIntroTour } from "@/lib/introTour";
import { clearSession, type Session } from "@/lib/session";

// The assistant (panel, cards, chat) is only needed once someone presses "Ask PaySense", so its
// code is loaded then, not with every page. It only renders after a click, in the browser.
const AssistantPanel = lazy(() =>
  import("@/components/assistant/AssistantPanel").then((m) => ({ default: m.AssistantPanel })),
);
// The intro replays only when asked for from the profile, so its code loads then.
const Onboarding = lazy(() =>
  import("@/components/onboarding/Onboarding").then((m) => ({ default: m.Onboarding })),
);
const Tour = lazy(() => import("@/components/onboarding/Tour").then((m) => ({ default: m.Tour })));

const subscribeNothing = () => () => {};

/** `hint` is the sidebar tooltip: what the page is for, in a line. */
type NavItem = { href: string; label: string; icon: string; hint: string };

/**
 * A navigation link that loads its page only when it is about to be used. Next's default would
 * prefetch every link on screen (all twelve sidebar pages at once); this prefetches on hover or
 * keyboard focus instead.
 */
function NavLink(props: Omit<ComponentProps<typeof Link>, "href" | "prefetch"> & { href: string }) {
  const router = useRouter();
  const prefetch = () => router.prefetch(props.href);
  return <Link {...props} prefetch={false} onMouseEnter={prefetch} onFocus={prefetch} />;
}
type NavGroup = { label: string; items: readonly NavItem[] };

// Grouped by what the student is doing. "Your data" sits with the profile, not in a group.
const NAV_GROUPS: readonly NavGroup[] = [
  {
    label: "Overview",
    items: [
      {
        href: "/", label: "Dashboard", icon: "◫",
        hint: "Where your money is heading, what you owe, and what to do next",
      },
      {
        href: "/insights", label: "Insights", icon: "✦",
        hint: "How your spending moved, with where every figure came from",
      },
    ],
  },
  {
    label: "Your money",
    items: [
      {
        href: "/transactions", label: "Transactions", icon: "≡",
        hint: "Everything you have logged or imported, a month at a time",
      },
      {
        href: "/categories", label: "Categories", icon: "#",
        hint: "The labels on your transactions, and your own",
      },
      {
        href: "/budgets", label: "Budgets", icon: "◎",
        hint: "Set a monthly spending limit per category and track it",
      },
      {
        href: "/recurring", label: "Recurring", icon: "↻",
        hint: "Rent, allowance, PTPTN and subscriptions on a schedule",
      },
      {
        href: "/import", label: "Import", icon: "⇪",
        hint: "Bring in a bank or e-wallet statement, or a spreadsheet",
      },
    ],
  },
  {
    label: "Buy now, pay later",
    items: [
      {
        href: "/risk", label: "Risk check", icon: "◔",
        hint: "See if a buy-now-pay-later purchase fits before you commit",
      },
      {
        href: "/plans", label: "Plans", icon: "▤",
        hint: "The instalment plans you have committed to, and what is left",
      },
    ],
  },
  {
    label: "How it works",
    items: [
      {
        href: "/model", label: "About the model", icon: "ⓘ",
        hint: "How the forecast, risk check and assistant work, and their limits",
      },
      {
        href: "/security", label: "Security drill", icon: "⛨",
        hint: "Attack the assistant on purpose and see what the defences stop",
      },
    ],
  },
];
const ALL_ITEMS = NAV_GROUPS.flatMap((group) => group.items);
// The phone's bottom bar: the four screens used most; everything else is under "More".
const PHONE_BAR = ["/", "/transactions", "/import", "/risk"].map(
  (href) => ALL_ITEMS.find((item) => item.href === href)!,
);

type Tone = "dark" | "light";

// The sidebar is the brand's teal, like the login panel: the one bold element of the app. Its
// links carry a cream focus ring, since the global teal ring would vanish on teal.
const TONE = {
  dark: {
    heading: "text-on-accent-muted",
    link: (active: boolean) =>
      active
        ? "bg-page font-semibold text-accent"
        : "text-on-accent hover:bg-accent-soft focus-visible:outline-on-accent",
  },
  light: {
    heading: "text-ink-muted",
    link: (active: boolean) =>
      active ? "bg-accent-bg font-semibold text-accent" : "text-ink hover:bg-surface-2",
  },
} as const;

function NavGroups({
  pathname,
  tone,
  onNavigate,
}: {
  pathname: string;
  tone: Tone;
  onNavigate?: () => void;
}) {
  const id = useId();
  return (
    <div className="flex flex-col gap-5">
      {NAV_GROUPS.map((group, g) => (
        <div key={group.label}>
          <p id={`${id}-${g}`} className={`mb-1.5 px-3 text-[12px] font-semibold ${TONE[tone].heading}`}>
            {group.label}
          </p>
          <ul aria-labelledby={`${id}-${g}`} className="flex flex-col gap-0.5">
            {group.items.map((item) => {
              const active = isActive(pathname, item.href);
              return (
                <li key={item.href}>
                  {/* Hover hints only beside the sidebar: the phone menu has no hover. */}
                  <Tooltip text={tone === "dark" ? item.hint : ""}>
                    {(describedBy) => (
                      <NavLink
                        href={item.href}
                        data-tour={item.href.slice(1) || undefined}
                        onClick={onNavigate}
                        aria-current={active ? "page" : undefined}
                        aria-describedby={describedBy}
                        className={`flex items-center gap-2.5 rounded-xl px-3 py-1.5 text-[14px] font-medium transition-[background-color,color,translate] duration-200 ${active ? "" : "hover:translate-x-0.5"} ${TONE[tone].link(active)}`}
                      >
                        <span aria-hidden className="w-4 text-center text-sm">
                          {item.icon}
                        </span>
                        {item.label}
                      </NavLink>
                    )}
                  </Tooltip>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}

function initials(name: string): string {
  const words = name.split(/\s+/).filter((word) => /^\p{L}/u.test(word));
  return words.slice(0, 2).map((word) => word[0].toUpperCase()).join("") || "?";
}

/** Who is signed in, their data, and the way out: at the foot of the sidebar and in "More". */
function Profile({
  user,
  tone,
  onLogout,
  onIntro,
  onNavigate,
}: {
  user: Session["user"];
  tone: Tone;
  onLogout: () => void;
  onIntro: () => void;
  onNavigate?: () => void;
}) {
  const dark = tone === "dark";
  const linkFocus = dark ? "focus-visible:outline-on-accent" : "";
  return (
    <div className={`rounded-2xl p-3 ${dark ? "bg-accent-deep" : "border border-line bg-surface-2"}`}>
      <div className="flex items-center gap-3">
        <span
          aria-hidden
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-rose font-display text-[15px] font-bold text-ink"
        >
          {initials(user.display_name)}
        </span>
        <div className="min-w-0">
          <p className={`truncate text-[14px] font-semibold ${dark ? "text-on-accent" : "text-ink"}`}>
            {user.display_name}
          </p>
          <p className={`truncate text-[12px] ${dark ? "text-on-accent-muted" : "text-ink-muted"}`}>
            {user.username}
          </p>
        </div>
      </div>
      <div className="mt-3 flex items-center justify-between gap-2">
        <Link
          href="/account"
          data-tour="data"
          onClick={onNavigate}
          className={`rounded-lg px-1 text-[13px] font-semibold underline-offset-2 hover:underline ${dark ? "text-on-accent" : "text-accent"} ${linkFocus}`}
        >
          Your data
        </Link>
        <button
          type="button"
          onClick={onLogout}
          className={`rounded-lg px-2 py-1 text-[13px] font-semibold ${
            dark ? "text-on-accent hover:bg-accent-soft" : "text-ink hover:bg-surface"
          } ${linkFocus}`}
        >
          Log out
        </button>
      </div>
      <button
        type="button"
        onClick={() => {
          onNavigate?.();
          onIntro();
        }}
        className={`mt-1 rounded-lg px-1 text-[12px] underline-offset-2 hover:underline ${
          dark ? "text-on-accent-muted" : "text-ink-muted"
        } ${linkFocus}`}
      >
        Show the intro again
      </button>
    </div>
  );
}

function Sidebar({
  pathname,
  user,
  onLogout,
  onIntro,
}: {
  pathname: string;
  user: Session["user"];
  onLogout: () => void;
  onIntro: () => void;
}) {
  return (
    <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col bg-accent px-3 py-5 md:flex">
      <Link
        href="/"
        className="mb-6 flex items-center gap-2.5 rounded-lg px-3 focus-visible:outline-on-accent"
      >
        <BrandMark className="h-9 w-9 shrink-0" />
        <span className="font-display text-[20px] font-bold tracking-tight text-on-accent">
          Pay<span className="text-rose">Sense</span>
        </span>
      </Link>
      <nav aria-label="Main navigation" className="-mx-1 min-h-0 flex-1 overflow-y-auto px-1">
        <NavGroups pathname={pathname} tone="dark" />
      </nav>
      <div className="mt-4">
        <Profile user={user} tone="dark" onLogout={onLogout} onIntro={onIntro} />
      </div>
    </aside>
  );
}

/** A phone has one navigation: this bar, with every other screen and the profile under "More". */
function MobileNav({
  pathname,
  user,
  onLogout,
  onIntro,
}: {
  pathname: string;
  user: Session["user"];
  onLogout: () => void;
  onIntro: () => void;
}) {
  const [open, setOpen] = useState(false);
  const inMore = !PHONE_BAR.some((item) => isActive(pathname, item.href));
  const itemClass = (active: boolean) =>
    `flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px] font-medium ${
      active ? "text-accent" : "text-ink-muted"
    }`;
  return (
    <>
      <nav
        aria-label="Quick navigation"
        className="fixed inset-x-0 bottom-0 z-40 flex border-t border-line bg-surface md:hidden"
      >
        {PHONE_BAR.map((item) => {
          const active = isActive(pathname, item.href);
          return (
            <NavLink
              key={item.href}
              href={item.href}
              data-tour={item.href.slice(1) || undefined}
              aria-current={active ? "page" : undefined}
              className={itemClass(active)}
            >
              <span aria-hidden className="text-base leading-none">
                {item.icon}
              </span>
              {item.label}
            </NavLink>
          );
        })}
        <button
          type="button"
          aria-haspopup="dialog"
          aria-expanded={open}
          data-tour="data"
          onClick={() => setOpen(true)}
          className={itemClass(inMore)}
        >
          <span aria-hidden className="text-base leading-none">
            ⋯
          </span>
          More
        </button>
      </nav>
      <Dialog open={open} title="Menu" onClose={() => setOpen(false)}>
        <div className="flex flex-col gap-5">
          <Profile
            user={user}
            tone="light"
            onLogout={onLogout}
            onIntro={onIntro}
            onNavigate={() => setOpen(false)}
          />
          <NavGroups pathname={pathname} tone="light" onNavigate={() => setOpen(false)} />
        </div>
      </Dialog>
    </>
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
  const intro = useIntroTour();
  // The tour of the app runs once per browser, on the dashboard, after the intro slides; read on
  // the server as not due, so it never flashes in a server render.
  const tourDue = useSyncExternalStore(subscribeNothing, () => introSeen() && !tourSeen(), () => false);
  const [tourEnded, setTourEnded] = useState(false); // covers a browser that will not store it
  const [tourReplay, setTourReplay] = useState(false);
  const touring = tourReplay || (pathname === "/" && tourDue && !tourEnded);
  const [prompt, setPrompt] = useState<{ text: string; n: number } | null>(
    null,
  );

  function openAssistant(text?: string) {
    if (text) setPrompt((current) => ({ text, n: (current?.n ?? 0) + 1 }));
    setAssistantOpen(true);
  }

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

  const endTour = useCallback(() => {
    markTourSeen();
    setTourEnded(true);
    setTourReplay(false);
  }, []);

  function handleLogout() {
    // Revoke on the server (every session of this user ends, D-49); the page does not wait for
    // it, and a failure still logs out locally.
    api.POST("/api/auth/logout").catch(() => undefined);
    clearSession();
    queryClient.clear();
    router.replace("/login");
  }

  return (
    <>
      {/* While the intro or the tour is over it, the app behind is inert: no focus, no clicks. */}
      <div className="flex min-h-screen" inert={intro.open || touring}>
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-lg focus:bg-ink focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-white"
        >
          Skip to content
        </a>
        <Sidebar pathname={pathname} user={user} onLogout={handleLogout} onIntro={intro.show} />
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-14 items-center justify-between gap-3 border-b border-line bg-surface px-4 sm:px-6">
            <Link
              href="/"
              className="flex items-center gap-2 font-display text-[17px] font-bold tracking-tight text-ink md:hidden"
            >
              <BrandMark className="h-7 w-7 shrink-0" />
              <span>
                Pay<span className="text-accent">Sense</span>
              </span>
            </Link>
            <div className="ml-auto flex items-center gap-3">
              <Button
                ref={askButton}
                data-tour="ask"
                variant="accent"
                size="sm"
                aria-expanded={assistantOpen}
                onClick={() =>
                  assistantOpen ? closeAssistant() : setAssistantOpen(true)
                }
              >
                Ask PaySense
              </Button>
            </div>
          </header>
          <main
            id="main"
            ref={main}
            tabIndex={-1}
            className="flex-1 px-4 py-6 pb-24 outline-none sm:px-6 md:pb-8"
          >
            <AssistantLauncher.Provider value={openAssistant}>
              {children}
            </AssistantLauncher.Provider>
          </main>
        </div>
        <MobileNav pathname={pathname} user={user} onLogout={handleLogout} onIntro={intro.show} />
        {assistantOpen && (
          <Suspense fallback={null}>
            <AssistantPanel onClose={closeAssistant} prompt={prompt} />
          </Suspense>
        )}
      </div>
      {intro.open && (
        <Suspense fallback={null}>
          <Onboarding
            slides
            onDone={() => {
              intro.close();
              setTourReplay(true); // a replay that runs to the end carries on into the tour
            }}
            onClose={intro.close}
          />
        </Suspense>
      )}
      {touring && (
        <Suspense fallback={null}>
          <Tour onDone={endTour} />
        </Suspense>
      )}
    </>
  );
}
